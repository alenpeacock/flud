#!/usr/bin/env python3

"""
FludNode.py (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL), verison 3.

FludNode is the process that runs to talk with other nodes in the flud backup network.
"""

import asyncio
from twisted.internet import reactor, defer
import threading, signal, sys, time, os, random, logging

from flud.FludConfig import FludConfig
from flud.protocol.FludServer import FludServer
from flud.protocol.AiohttpServer import FludAiohttpServer
from flud.protocol.FludClient import FludClient
from flud.protocol.FludCommUtil import getCanonicalIP
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
        self._use_async_server = os.environ.get("FLUD_ASYNCIO_SERVER") == "1"
        self._reactor_thread = None
        self._owns_reactor = False
        self._async_tasks = []

    def _start_reactor_background(self):
        if reactor.running:
            return
        self._owns_reactor = True
        self._reactor_thread = threading.Thread(
                target=reactor.run,
                kwargs={"installSignalHandlers": 0},
                daemon=True,
        )
        self._reactor_thread.start()
        # Give reactor a moment to enter running state for Deferred scheduling.
        deadline = time.time() + 5.0
        while not reactor.running and time.time() < deadline:
            time.sleep(0.01)

    def _initLogger(self):
        logger = logging.getLogger('flud')
        self.screenhandler = logging.StreamHandler()
        self.screenhandler.setLevel(logging.INFO)
        logger.addHandler(self.screenhandler)
        self.logger = logger

    def pingRandom(self, tstamp):
        return
        # XXX: see pg. 4, Section 2.2 (short) or 2.3 (long) of the Kademlia
        #      paper -- once an hour, each node should check any buckets that
        #      haven't been refreshed and pick a random id within that space
        #      to findnode(id) on, for all buckets.
        if tstamp < self.DHTtstamp: 
            #r = random.randrange(2**256)
            n = self.config.routing.knownExternalNodes()
            if len(n) > 2:
                n1 = random.choice(n)[2]
                n2 = random.choice(n)[2]
                r = (n1+n2)/2
            else:
                r = random.randrange(2**256)
            def badNode(error):
                node.logger.warn("Couldn't ping %s:%s" % 
                        (sys.argv[1], sys.argv[2]))
            d = self.client.kFindNode(r)
            d.addErrback(badNode)
        pingtime = random.randrange(PINGTIME/2, PINGTIME)
        reactor.callLater(pingtime, self.pingRandom, time.time())

    def syncConfig(self):
        self.config.save()
        reactor.callLater(SYNCTIME, self.syncConfig)

    async def _async_sync_loop(self):
        while True:
            await asyncio.sleep(SYNCTIME)
            self.config.save()

    def _schedule_async_tasks(self):
        self._async_tasks.append(self.async_runtime.submit(self._async_sync_loop()))

    def start(self, twistd=False):
        """ starts the reactor in this thread """
        if self._use_async_server:
            self.webserver = FludAiohttpServer(self, self.config.port)
            self.logger.log(logging.INFO,
                    "FludAiohttpServer starting on %d"
                    % self.config.port)
            self.webserver.start()
            self._schedule_async_tasks()
            if not twistd:
                self.join()
        else:
            self.webserver = FludServer(self, self.config.port)
            self.logger.log(logging.INFO, "FludServer starting")
            reactor.callLater(1, self.pingRandom, time.time())
            reactor.callLater(random.randrange(10), self.syncConfig)
            if not twistd:
                reactor.run()

    def run(self):
        """ starts the reactor in its own thread """
        #signal.signal(signal.SIGINT, self.sighandler)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        if self._use_async_server:
            self.webserver = FludAiohttpServer(self, self.config.port)
            self._schedule_async_tasks()
        else:
            self.webserver = FludServer(self, self.config.port)
        self.webserver.start()
        # XXX: need to do save out current config every X seconds
        # XXX: need to seperate known_nodes from config, and then update this
        # every X seconds.  only update config when it changes.
    
    def stop(self):
        self.logger.log(logging.INFO, "shutting down FludNode")
        self.webserver.stop()
        for task in self._async_tasks:
            task.cancel()
        self._async_tasks = []
        self.async_http.close()
        self.async_runtime.stop()
        if self._owns_reactor and reactor.running:
            reactor.callFromThread(reactor.stop)

    def join(self):
        self.webserver.join()
        if self._reactor_thread is not None:
            self._reactor_thread.join()

    def sighandler(self, sig, frame):
        self.logger.log(logging.INFO, "handling signal %s" % sig)
    
    def connectViaGateway(self, host, port):
        if self._use_async_server:
            self._async_tasks.append(
                self.async_runtime.submit(self._async_connectViaGateway(host, port))
            )
            return

        def refresh(knodes):
            
            def refreshDone(results):
                self.logger.info("bucket refreshes finished: %s" % results)
                print("flud node connected and listening on port %d"\
                        % self.config.port)
            
            #print "found knodes %s" % knodes
            dlist = []
            for bucket in self.config.routing.kBuckets:
                #if True:
                if bucket.begin <= self.config.routing.node[2] < bucket.end:
                    pass
                    #print "passed on bucket %x-%s" % (bucket.begin, bucket.end)
                else:
                    begin = int(bucket.begin)
                    end = int(bucket.end)
                    if end <= begin:
                        continue
                    refreshID = random.randrange(begin, end)
                    #print "refreshing bucket %x-%x by finding %x" \
                    #       % (bucket.begin, bucket.end, refreshID)
                    self.logger.info("refreshing bucket %x-%x by finding %x"
                            % (bucket.begin, bucket.end, refreshID))
                    deferred = self.client.kFindNode(refreshID)
                    dlist.append(deferred) 
            dl = defer.DeferredList(dlist, consumeErrors=True)
            dl.addCallback(refreshDone)
            # XXX: do we need to ping newly discovered known nodes?  If not,
            #      we could be vulnerable to a poisoning attack (at first
            #      glance, this attack seems rather impotent...)
            # XXX: need to call refresh about every 60 minutes.  Add a 
            #      reactor.callLater here to do it.
            
        max_attempts = int(os.environ.get("FLUDGWRETRIES", "20"))
        initial_delay = float(os.environ.get("FLUDGWRETRY_DELAY", "0.5"))
        max_delay = float(os.environ.get("FLUDGWRETRY_MAX_DELAY", "10.0"))
        request_timeout = float(os.environ.get("FLUDGWCONNECT_TIMEOUT", "5.0"))
        state = {"attempt": 0, "delay": initial_delay}

        def badGW(error):
            state["attempt"] += 1
            self.logger.warning("gateway connect attempt %d/%d to %s:%s failed: %s"
                    % (state["attempt"], max_attempts, host, port, str(error)))
            if state["attempt"] >= max_attempts:
                self.logger.error("giving up gateway connection to %s:%s after %d attempts"
                        % (host, port, max_attempts))
                return error
            delay = min(state["delay"], max_delay)
            self.logger.info("retrying gateway connection to %s:%s in %.1fs"
                    % (host, port, delay))
            state["delay"] = min(max_delay, state["delay"] * 2)
            reactor.callLater(delay, connect)
            return None

        def connect():
            self.logger.debug("connectViaGateway %s:%d" % (host, port))
            deferred = self.client.sendkFindNode(host, port,
                    self.config.routing.node[2])
            # Async client calls can hang on connect/DNS; bound each attempt so
            # gateway bootstrap can progress via retries.
            if request_timeout > 0:
                try:
                    deferred.addTimeout(request_timeout, reactor)
                except Exception:
                    pass
            deferred.addCallback(refresh)
            deferred.addErrback(badGW)

        connect()

    async def _async_connectViaGateway(self, host, port):
        max_attempts = int(os.environ.get("FLUDGWRETRIES", "20"))
        initial_delay = float(os.environ.get("FLUDGWRETRY_DELAY", "0.5"))
        max_delay = float(os.environ.get("FLUDGWRETRY_MAX_DELAY", "10.0"))
        request_timeout = float(os.environ.get("FLUDGWCONNECT_TIMEOUT", "5.0"))
        delay = initial_delay

        for attempt in range(1, max_attempts + 1):
            try:
                deferred = self.client.sendkFindNode(host, port,
                        self.config.routing.node[2])
                if request_timeout > 0:
                    try:
                        deferred.addTimeout(request_timeout, reactor)
                    except Exception:
                        pass
                knodes = await asyncio.wrap_future(
                    self.async_runtime.submit(
                        self._await_deferred_result(deferred)
                    )
                )
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

    async def _await_deferred_result(self, deferred):
        future = asyncio.get_running_loop().create_future()

        def _cb(result):
            if not future.done():
                future.set_result(result)
            return result

        def _eb(err):
            exc = getattr(err, "value", err)
            if not future.done():
                future.set_exception(exc)
            return None

        deferred.addCallbacks(_cb, _eb)
        return await future

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
                asyncio.wrap_future(
                    self.async_runtime.submit(
                        self._await_deferred_result(self.client.kFindNode(refreshID))
                    )
                )
            )
        if dlist:
            results = await asyncio.gather(*dlist, return_exceptions=True)
            self.logger.info("bucket refreshes finished: %s" % results)

def getPath():
    # this is a hack to be able to get the location of FludNode.tac
    return os.path.dirname(os.path.abspath(__file__))
