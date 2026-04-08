import asyncio
import binascii
import logging
import os
import smtplib
from email.message import EmailMessage

from Cryptodome.Cipher import AES

from flud.FludCrypto import FludRSA, generateRandom, hashstring
import flud.FludFileOperations as FileOps
from flud.fencode import fencode, fdecode
from flud.async_runtime import maybe_await

logger = logging.getLogger("flud.local.async_server")

MAXCONCURRENT = 300
CHALLENGE_LENGTH = 40


def _diag_enabled():
    return os.environ.get("FLUD_ASYNC_DIAG") == "1"


class AsyncLocalServer:
    COMMAND_LIMITS = {
        "PUTF": MAXCONCURRENT,
        "GETF": MAXCONCURRENT,
        "GETI": MAXCONCURRENT,
        "FNDN": 1,
        "STOR": MAXCONCURRENT,
        "RTRV": MAXCONCURRENT,
        "VRFY": MAXCONCURRENT,
        "FNDV": 1,
        "CRED": 1,
        "LIST": 1,
        "GETM": 1,
        "PUTM": 1,
    }

    def __init__(self, node):
        self.node = node
        self.config = node.config
        self._server = None
        self._challenges = {}
        self._semaphores = {
            command: asyncio.Semaphore(limit)
            for command, limit in self.COMMAND_LIMITS.items()
        }

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_client,
            host="127.0.0.1",
            port=self.node.config.clientport,
        )
        logger.info("async local protocol listening on 127.0.0.1:%d",
                self.node.config.clientport)

    async def stop(self):
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    def sendChallenge(self):
        challenge = fencode(generateRandom(CHALLENGE_LENGTH))
        self._challenges[challenge] = asyncio.get_running_loop().time() + 60.0
        echallenge = self.config.Ku.encrypt(challenge)[0]
        return fencode(echallenge)

    def challengeAnswered(self, response):
        expiry = self._challenges.get(response)
        if expiry is None:
            return False
        if expiry < asyncio.get_running_loop().time():
            self._challenges.pop(response, None)
            return False
        self._challenges.pop(response, None)
        return True

    async def _handle_client(self, reader, writer):
        authenticated = False
        peer = writer.get_extra_info("peername")
        logger.info("local client connected: %s", peer)
        try:
            while not reader.at_eof():
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("utf-8").rstrip("\r\n")
                if len(line) < 5:
                    continue
                command = line[0:4]
                status = line[4]
                data = line[5:]
                if not authenticated and command == "AUTH":
                    authenticated = await self._handle_auth(status, data, writer)
                    continue
                if not authenticated:
                    await self._write(writer, "AUTH!\r\n")
                    continue
                if command == "DIAG":
                    await self._handle_diag(data, writer)
                    continue
                if status == "?":
                    asyncio.create_task(
                        self._run_command(command, data, writer)
                    )
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_auth(self, status, data, writer):
        if status == "?":
            await self._write(writer, "AUTH?%s\r\n" % self.sendChallenge())
            return False
        if status == ":" and self.challengeAnswered(data):
            await self._write(writer, "AUTH:\r\n")
            return True
        await self._write(writer, "AUTH!\r\n")
        return False

    async def _handle_diag(self, data, writer):
        if data == "NODE":
            nodetups = self.config.routing.knownExternalNodes()
            nodes = []
            for node in nodetups:
                entry = list(node)
                entry.append(self.config.reputations.get(node[2], 0))
                entry.append(self.config.throttled.get(node[2], 0))
                nodes.append(tuple(entry))
            await self._write(writer, "DIAG:NODE%s\r\n" % fencode(nodes))
            return
        if data == "BKTS":
            buckets = eval("%s" % self.config.routing.kBuckets)
            await self._write(writer, "DIAG:BKTS%s\r\n" % fencode(buckets))
            return
        command = data[:4]
        payload = data[5:]
        await self._run_command(command, payload, writer, prepend="DIAG")

    async def _run_command(self, command, data, writer, prepend=None):
        semaphore = self._semaphores[command]
        async with semaphore:
            if _diag_enabled():
                logger.warning("local command start %s %s", command, data[:120])
            try:
                result = await self._doOp(command, data)
            except Exception as exc:
                logger.exception("local command failed %s %s", command, data[:120])
                await self._sendFailure(writer, exc, command, data, prepend)
                return
            if _diag_enabled():
                logger.warning("local command done %s %s", command, data[:120])
            await self._sendSuccess(writer, result, command, data, prepend)

    async def _run_fileop(self, operation, *args):
        if _diag_enabled():
            logger.warning("dispatching fileop %s via async runtime", operation.__name__)
        future = self.node.async_runtime.submit(operation(*args))
        return await asyncio.wrap_future(future)

    async def _doOp(self, command, fname):
        if command == "PUTF":
            return await self._run_fileop(FileOps.store_file, self.node, fname)
        if command == "GETI":
            return await self._run_fileop(FileOps.retrieve_file, self.node, fname)
        if command == "GETF":
            return await self._run_fileop(FileOps.retrieve_filename, self.node, fname)
        if command == "FNDN":
            return await self.node.client.k_find_node(int(fname, 16))
        if command == "FNDV":
            return await self.node.client.k_find_value(int(fname, 16))
        if command == "CRED":
            passphrase, email = fdecode(fname)
            passphrase = self.config.Kr.decrypt(passphrase)
            private_key = self.config.Kr.exportPrivateKey()
            private_key["g"] = self.config.groupIDr
            encoded = fencode(private_key)
            key = AES.new(
                binascii.unhexlify(hashstring(passphrase)),
                AES.MODE_ECB,
            )
            encoded = "\x00" * (16 - (len(encoded) % 16)) + encoded
            payload = fencode(key.encrypt(encoded))
            message = EmailMessage()
            message["Subject"] = "Your encrypted flud credentials"
            message["From"] = "your_flud_client@localhost"
            message["To"] = email
            message.set_content(
                "Hopefully, you'll never need to use this email.  Its "
                "sole purpose is to help you recover your data after a "
                "catastrophic and complete loss of the original computer "
                "or hard drive.\n\n"
                "In that unlucky event, you'll need a copy of your flud "
                "credentials, which I've included below, sitting between "
                "the \"---+++---\" markers.  These credentials were "
                "encrypted with a passphrase of your choosing when you "
                "installed the flud software.\n\n"
                "---+++---\n" + payload + "\n---+++---\n"
            )
            return await asyncio.to_thread(
                self._send_mail,
                "localhost",
                "your_flud_client@localhost",
                email,
                message.as_string(),
            )
        if command == "LIST":
            return self.config.master
        if command == "GETM":
            return await self._run_fileop(FileOps.retrieve_master_index, self.node)
        if command == "PUTM":
            return await self._run_fileop(FileOps.update_master_index, self.node)
        host = fname[:fname.find(":")]
        port = fname[fname.find(":") + 1:fname.find(",")]
        fname = fname[fname.find(",") + 1:]
        if command == "STOR":
            return await self.node.client.store(fname, None, host, int(port))
        if command == "RTRV":
            return await self.node.client.retrieve(fname, host, int(port))
        if command == "VRFY":
            offset = port[port.find(":") + 1:port.find("-")]
            length = port[port.find("-") + 1:]
            port = port[:port.find(":")]
            return await self.node.client.verify(
                fname, int(offset), int(length), host, int(port)
            )
        raise ValueError("bad op")

    async def _sendSuccess(self, writer, response, command, data, prepend=None):
        if prepend:
            payload = "%s:%s %s:%s\r\n" % (prepend, command, fencode(response), data)
        else:
            payload = "%s:%s:%s\r\n" % (command, fencode(response), data)
        await self._write(writer, payload)

    async def _sendFailure(self, writer, err, command, data, prepend=None):
        message = getattr(err, "getErrorMessage", None)
        if callable(message):
            message = message()
        if not message:
            message = str(err)
        if prepend:
            payload = "%s!%s %s!%s\r\n" % (prepend, command, message, data)
        else:
            payload = "%s!%s!%s\r\n" % (command, message, data)
        await self._write(writer, payload)

    async def _write(self, writer, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        writer.write(data)
        await writer.drain()

    def _send_mail(self, host, from_addr, to_addr, message):
        with smtplib.SMTP(host) as client:
            client.sendmail(from_addr, [to_addr], message)
        return True
