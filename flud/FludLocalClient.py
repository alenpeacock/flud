#!/usr/bin/env python3

import asyncio
import logging
import os
import sys
import time

from flud.FludConfig import FludConfig
from flud.FludCrypto import hashfile
from flud.fencode import fencode

from .protocol.AsyncLocalClient import AsyncLocalClient

logger = logging.getLogger("flud")


class CmdClient:
    def __init__(self, config):
        self.config = config
        self.client = AsyncLocalClient(config)
        self.quit = False

    async def connect(self):
        await self.client.connect()

    async def run(self):
        while not self.quit:
            try:
                command = await asyncio.to_thread(input, "%s> " % time.ctime())
            except EOFError:
                break
            await self.handle_command(command.strip())

    async def handle_command(self, command):
        if not command:
            return
        commands = command.split(" ")
        commandkey = commands[0][:4]

        help_dict = {
            "exit": "exit from the client",
            "help": "display this help message",
            "putf": "store a file: 'putf canonicalfilepath'",
            "getf": "retrieve a file: 'getf canonicalfilepath'",
            "geti": "retrieve a file by CAS key: 'geti fencodedCASkey'",
            "fndn": "send a FINDNODE() message: 'fndn hexIDstring'",
            "list": "list stored files (read from local metadata)",
            "putm": "store manifest",
            "getm": "retrieve manifest",
            "node": "list known nodes",
            "buck": "print k buckets",
            "stor": "store a block to a given node: 'stor host:port,fname'",
            "rtrv": "retrieve a block from a given node: 'rtrv host:port,fname'",
            "vrfy": "verify a block on a given node: 'vrfy host:port:offset-length,fname'",
            "fndv": "retrieve a value from the DHT: 'fndv hexkey'",
        }

        if commandkey in {"exit", "quit"}:
            self.quit = True
            return
        if commandkey == "help":
            for key in sorted(help_dict):
                print("%s:\t %s" % (key, help_dict[key]))
            return

        try:
            if commandkey == "putf":
                result = await self.client.sendPUTF(commands[1])
            elif commandkey == "getf":
                result = await self.client.sendGETF(commands[1])
            elif commandkey == "geti":
                result = await self.client.sendGETI(commands[1])
            elif commandkey == "fndn":
                result = await self.client.sendFNDN(commands[1])
            elif commandkey == "list":
                result = await self.client.sendLIST()
            elif commandkey == "putm":
                result = await self.client.sendPUTM()
            elif commandkey == "getm":
                result = await self.client.sendGETM()
            elif commandkey == "node":
                result = await self.client.sendDIAGNODE()
            elif commandkey == "buck":
                result = await self.client.sendDIAGBKTS()
            elif commandkey == "stor":
                storcommands = commands[1].split(",")
                try:
                    int(storcommands[1], 16)
                except Exception:
                    linkfile = fencode(int(hashfile(storcommands[1]), 16))
                    if os.path.islink(linkfile):
                        os.remove(linkfile)
                    os.symlink(storcommands[1], linkfile)
                    storcommands[1] = linkfile
                result = await self.client.sendDIAGSTOR(
                    "%s,%s" % (storcommands[0], storcommands[1])
                )
            elif commandkey == "rtrv":
                result = await self.client.sendDIAGRTRV(commands[1])
            elif commandkey == "vrfy":
                result = await self.client.sendDIAGVRFY(commands[1])
            elif commandkey == "fndv":
                result = await self.client.sendDIAGFNDV(commands[1])
            else:
                print("illegal command '%s'" % command)
                return
            print(result)
        except Exception as exc:
            print("bah!: %s" % exc)


async def _main_async():
    config = FludConfig()
    config.load(doLogging=False)

    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler("/tmp/fludclient.log")
    formatter = logging.Formatter(
        "%(asctime)s %(filename)s:%(lineno)d %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if len(sys.argv) == 2:
        config.clientport = int(sys.argv[1])

    print("connecting to localhost:%d" % config.clientport)
    cmd_client = CmdClient(config)
    await cmd_client.connect()
    await cmd_client.run()
    await cmd_client.client.close()


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
