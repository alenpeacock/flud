import asyncio
import logging
import os

from flud.fencode import fdecode, fencode

logger = logging.getLogger("flud.local.async_client")


class AsyncLocalClient:
    def __init__(self, config, host="127.0.0.1", port=None):
        self.config = config
        self.host = host
        self.port = port if port is not None else config.clientport
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()

    async def connect(self):
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )
        await self._authenticate()

    async def close(self):
        if self._writer is None:
            return
        self._writer.close()
        await self._writer.wait_closed()
        self._reader = None
        self._writer = None

    async def _authenticate(self):
        response = await self._send_line("AUTH?")
        if response[0] != "AUTH" or response[1] != "?":
            raise RuntimeError("unexpected auth challenge response")
        challenge = response[2]
        challenge = (fdecode(challenge),)
        answer = self.config.Kr.decrypt(challenge)
        if isinstance(answer, bytes):
            answer = answer.decode("utf-8")
        response = await self._send_line("AUTH:%s" % answer)
        if response[0] != "AUTH" or response[1] != ":":
            raise RuntimeError("authentication failed")

    async def _send_line(self, line):
        if self._writer is None:
            await self.connect()
        self._writer.write((line + "\r\n").encode("utf-8"))
        await self._writer.drain()
        raw = await self._reader.readline()
        if not raw:
            raise ConnectionError("connection closed by local server")
        decoded = raw.decode("utf-8").rstrip("\r\n")
        command = decoded[:4]
        status = decoded[4]
        data = decoded[5:]
        return command, status, data

    async def request(self, command, data=""):
        async with self._lock:
            response_command, status, payload = await self._send_line(
                "%s?%s" % (command, data)
            )
        if response_command == "DIAG":
            subcommand = payload[:4]
            payload = payload[4:]
            response_command = subcommand
        if status == ":":
            if command in {"NODE", "BKTS"}:
                return payload
            if ":" in payload:
                response, _orig = payload.split(":", 1)
                return fdecode(response)
            return fdecode(payload) if payload else None
        if status == "!":
            if "!" in payload:
                message, _orig = payload.split("!", 1)
                raise RuntimeError(message)
            raise RuntimeError(payload)
        if status == "?":
            return payload
        raise RuntimeError("unexpected response %s%s%s" % (
            response_command, status, payload))

    async def sendPUTF(self, fname):
        if os.path.isdir(fname):
            results = []
            for entry in os.listdir(fname):
                results.append(await self.sendPUTF(os.path.join(fname, entry)))
            return results
        return await self.request("PUTF", fname)

    async def sendGETI(self, fid):
        return await self.request("GETI", fid)

    async def sendGETF(self, fname):
        return await self.request("GETF", fname)

    async def sendFNDN(self, node_id):
        return await self.request("FNDN", node_id)

    async def sendLIST(self):
        return await self.request("LIST")

    async def sendGETM(self):
        return await self.request("GETM")

    async def sendPUTM(self):
        return await self.request("PUTM")

    async def sendDIAGNODE(self):
        async with self._lock:
            command, status, payload = await self._send_line("DIAG?NODE")
        if command != "DIAG" or status != ":":
            raise RuntimeError(payload)
        return fdecode(payload[4:])

    async def sendDIAGBKTS(self):
        async with self._lock:
            command, status, payload = await self._send_line("DIAG?BKTS")
        if command != "DIAG" or status != ":":
            raise RuntimeError(payload)
        return fdecode(payload[4:])

    async def sendDIAGSTOR(self, command):
        async with self._lock:
            resp_command, status, payload = await self._send_line("DIAG?STOR %s" % command)
        return self._decode_diag_response(resp_command, status, payload)

    async def sendDIAGRTRV(self, command):
        async with self._lock:
            resp_command, status, payload = await self._send_line("DIAG?RTRV %s" % command)
        return self._decode_diag_response(resp_command, status, payload)

    async def sendDIAGVRFY(self, command):
        async with self._lock:
            resp_command, status, payload = await self._send_line("DIAG?VRFY %s" % command)
        return self._decode_diag_response(resp_command, status, payload)

    async def sendDIAGFNDV(self, value):
        return await self.request("FNDV", value)

    def _decode_diag_response(self, response_command, status, payload):
        if response_command != "DIAG":
            raise RuntimeError("unexpected diag response")
        subcommand = payload[:4]
        body = payload[4:]
        if status == ":":
            response, _orig = body.split(":", 1)
            return fdecode(response)
        if status == "!":
            message, _orig = body.split("!", 1)
            raise RuntimeError(message)
        raise RuntimeError("unexpected diag status %s for %s" % (status, subcommand))
