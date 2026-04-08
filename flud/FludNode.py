#!/usr/bin/env python3

"""
FludNode.py (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL), verison 3.

FludNode is the process that runs to talk with other nodes in the flud backup network.
"""

import asyncio
import signal
import time
import os
import random
import logging

from flud.FludConfig import FludConfig
from flud.protocol.AiohttpServer import FludAiohttpServer
from flud.protocol.FludClient import FludClient
from flud.async_runtime import AsyncHTTPClient, AsyncRuntime

PINGTIME=60
SYNCTIME=900

class FludNode(object):
    """
    A node in the flud network.  A node is both a client and a server.  It
    listens on a network accessible port for both DHT and Storage layer
    requests, and it listens on a local port for client interface commands.
    """
    
    def __init__(self, port=None):
        self._initLogger()
        self.config = FludConfig()
        self.logger.removeHandler(self.screenhandler)
        self.config.load(serverport=port)
        self.client = FludClient(self)
        self.async_runtime = AsyncRuntime()
        self.async_runtime.start()
        self.async_http = AsyncHTTPClient(self.async_runtime)
        self.DHTtstamp = time.time()+10
        self._use_async_server = True
        self._async_tasks = []

    def _initLogger(self):
        logger = logging.getLogger('flud')
        self.screenhandler = logging.StreamHandler()
        self.screenhandler.setLevel(logging.INFO)
        logger.addHandler(self.screenhandler)
        self.logger = logger

    async def _async_sync_loop(self):
        while True:
            await asyncio.sleep(SYNCTIME)
            self.config.save()

    def _schedule_async_tasks(self):
        self._async_tasks.append(self.async_runtime.submit(self._async_sync_loop()))

    def start(self, twistd=False):
        """Starts the asyncio server in this thread."""
        self.logger.log(logging.INFO,
                "FludAiohttpServer starting on %d" % self.config.port)
        self.run()
        if not twistd:
            self.join()

    def run(self):
        """Starts the asyncio server in its own thread."""
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        self.webserver = FludAiohttpServer(self, self.config.port)
        self._schedule_async_tasks()
        self.webserver.start()
    
    def stop(self):
        self.logger.log(logging.INFO, "shutting down FludNode")
        self.webserver.stop()
        for task in self._async_tasks:
            task.cancel()
        self._async_tasks = []
        self.async_http.close()
        self.async_runtime.stop()

    def join(self):
        self.webserver.join()

    def sighandler(self, sig, frame):
        self.logger.log(logging.INFO, "handling signal %s" % sig)
    
    def connectViaGateway(self, host, port):
        self._async_tasks.append(
            self.async_runtime.submit(self._async_connectViaGateway(host, port))
        )

    async def _async_connectViaGateway(self, host, port):
        max_attempts = int(os.environ.get("FLUDGWRETRIES", "20"))
        initial_delay = float(os.environ.get("FLUDGWRETRY_DELAY", "0.5"))
        max_delay = float(os.environ.get("FLUDGWRETRY_MAX_DELAY", "10.0"))
        request_timeout = float(os.environ.get("FLUDGWCONNECT_TIMEOUT", "5.0"))
        delay = initial_delay

        for attempt in range(1, max_attempts + 1):
            try:
                if request_timeout > 0:
                    knodes = await asyncio.wait_for(
                        self.client.send_k_find_node(
                            host, port, self.config.routing.node[2]),
                        timeout=request_timeout)
                else:
                    knodes = await self.client.send_k_find_node(
                        host, port, self.config.routing.node[2])
                await self._async_refresh_buckets(knodes)
                print("flud node connected and listening on port %d"
                        % self.config.port)
                return
            except Exception as error:
                self.logger.warning(
                    "gateway connect attempt %d/%d to %s:%s failed: %s",
                    attempt, max_attempts, host, port, str(error)
                )
                if attempt >= max_attempts:
                    self.logger.error(
                        "giving up gateway connection to %s:%s after %d attempts",
                        host, port, max_attempts
                    )
                    raise
                await asyncio.sleep(min(delay, max_delay))
                delay = min(max_delay, delay * 2)

    async def _async_refresh_buckets(self, knodes):
        dlist = []
        for bucket in self.config.routing.kBuckets:
            if bucket.begin <= self.config.routing.node[2] < bucket.end:
                continue
            begin = int(bucket.begin)
            end = int(bucket.end)
            if end <= begin:
                continue
            refreshID = random.randrange(begin, end)
            dlist.append(
                self.client.k_find_node(refreshID)
            )
        if dlist:
            results = await asyncio.gather(*dlist, return_exceptions=True)
            self.logger.info("bucket refreshes finished: %s" % results)

def getPath():
    # this is a hack to be able to get the location of FludNode.tac
    return os.path.dirname(os.path.abspath(__file__))
