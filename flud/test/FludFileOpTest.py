#!/usr/bin/env python3

"""
FludFileOpTest.py,  (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

System tests for FludFileOperations
"""

import asyncio
import sys, os, time, logging, tempfile, shutil, faulthandler, signal
import socket
from zlib import crc32

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from flud.FludNode import FludNode
import flud.defer as defer
from flud.fencode import fdecode
from flud.FludCrypto import generateRandom
from flud.FludFileOperations import *

failure = defer.failure


def listMeta(config):
    with open(os.path.join(config.metadir, config.metamaster), 'r') as fmaster:
        master = fmaster.read()
    if master == "":
        return {}
    return fdecode(master)


def gather_deferreds(node, deferreds):
    async def _gather():
        results = await asyncio.gather(
            *(maybe_await(d) for d in deferreds),
            return_exceptions=True,
        )
        normalized = []
        for result in results:
            if isinstance(result, Exception):
                normalized.append((False, result))
            else:
                normalized.append((True, result))
        for success, result in normalized:
            if not success:
                raise result
        return normalized
    return node.async_runtime.deferred_from_coro(_gather())

logger = logging.getLogger('flud')
#logging.basicConfig(level=logging.DEBUG)
#logger.setLevel(logging.DEBUG)
#logging.getLogger('flud.fileops').setLevel(logging.DEBUG)


def testError(failure, message, node):
    print("testError message: %s" % message)
    print("testError: %s" % str(failure))
    print("At least 1 test FAILED")
    return failure

def verifySuccess(r, desc):
    print("%s succeeded" % desc)

def checkRetrieveFile(res, node, fname):
    retrieved = res
    if isinstance(res, (list, tuple)) and res:
        retrieved = res[0]
    if isinstance(retrieved, str) and os.path.exists(retrieved):
        with open(fname, "rb") as f:
            orig_crc = 0
            for chunk in iter(lambda: f.read(65536), b""):
                orig_crc = crc32(chunk, orig_crc)
        with open(retrieved, "rb") as f:
            retrieved_crc = 0
            for chunk in iter(lambda: f.read(65536), b""):
                retrieved_crc = crc32(chunk, retrieved_crc)
        orig_crc &= 0xFFFFFFFF
        retrieved_crc &= 0xFFFFFFFF
        if orig_crc != retrieved_crc:
            return defer.fail(failure.DefaultException(
                "crc mismatch for %s (expected %08x, got %08x)" % (
                    retrieved, orig_crc, retrieved_crc)))
    print("retrieve of %s succeeded" % fname)
    return res  # <- *VITAL* for concurrent dup ops to succeed.

def testRetrieveFile(node, fname):
    d = RetrieveFilename(node, fname).deferred
    d.addCallback(checkRetrieveFile, node, fname)
    d.addErrback(testError, fname, node)
    return d

def retrieveSequential(r, node, filenamelist, desc):
    def loop(r, node, filenamelist, desc):
        if filenamelist:
            fname = filenamelist.pop()
            print("testing retrieve (%s) %s" % (desc, fname))
            d = testRetrieveFile(node, fname)
            d.addCallback(loop, node, filenamelist, desc)
            d.addErrback(testError)
            return d
        else:
            print("retrieve sequential (%s) done" % desc)

    print("test retrieveSequential %s" % desc)
    return loop(None, node, filenamelist, desc)

def storeSuccess(r, desc):
    print("%s succeeded" % desc)

def storeConcurrent(r, node, files, desc):
    #print "r was %s" % r
    print("test storeConcurrent %s" % desc)
    dlist = []
    for file in files:
        d = testStoreFile(node, file)
        dlist.append(d)
    dl = gather_deferreds(node, dlist)
    dl.addCallback(storeSuccess, desc)
    dl.addErrback(testError)
    return dl

def checkStoreFile(res, node, fname):
    master = listMeta(node.config)
    if fname not in master:
        return defer.fail(failure.DefaultException("file not stored"))
    else:
        print("store of %s appeared successful" % fname)
    return res  # <- *VITAL* for concurrent dup ops to succeed.

def testStoreFile(node, fname):
    d = StoreFile(node, fname).deferred
    d.addCallback(checkStoreFile, node, fname)
    d.addErrback(testError, fname, node)
    return d


def doTests(node, smallfnames, largefnames, dupsmall, duplarge):
    d = testStoreFile(node, smallfnames[0])
    d.addCallback(storeConcurrent, node, smallfnames, "small")
    d.addCallback(storeConcurrent, node, largefnames, "large")
    d.addCallback(storeConcurrent, node, dupsmall, "small duplicates")
    d.addCallback(storeConcurrent, node, duplarge, "large duplicates")

    #d = storeConcurrent(None, node, dupsmall, "small duplicates")
    #d = storeConcurrent(None, node, duplarge, "large duplicates")
    
    d.addCallback(retrieveSequential, node, smallfnames, "small")
    d.addCallback(retrieveSequential, node, largefnames, "large")
    d.addCallback(retrieveSequential, node, dupsmall, "small duplicates")
    d.addCallback(retrieveSequential, node, duplarge, "large duplicates")

    return d

def cleanup(_, node, filenamelist):
    #print _
    for f in filenamelist:
        try:
            print("deleting %s" % f)
            os.remove(f)
        except:
            print("couldn't remove %s" % f)
    node.async_runtime.loop.call_soon_threadsafe(node.stop)

def generateTestFile(minSize):
    fname = tempfile.mktemp()
    f = open(fname, 'wb')
    data = generateRandom(minSize//50)
    for i in range(0, 51+random.randrange(50)):
        f.write(data)
    f.close()
    filename = os.path.join("/tmp",fname)
    os.rename(fname,filename)
    return filename

def ensureGatewayReachable(host, port):
    timeout = float(os.environ.get("FLUD_TEST_GATEWAY_CONNECT_TIMEOUT", "2.0"))
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return
    except OSError as exc:
        raise RuntimeError(
            "gateway %s:%s is not reachable (%s). Start a flud node there "
            "before running this test." % (host, port, str(exc))
        )


def waitForRoutingPopulation(node):
    min_known = int(os.environ.get("FLUD_FILEOP_MIN_KNOWN_NODES", "1"))
    timeout = float(os.environ.get("FLUD_FILEOP_ROUTE_TIMEOUT", "15.0"))
    deadline = time.time() + timeout
    while time.time() < deadline:
        known = len(node.config.routing.knownExternalNodes())
        if known >= min_known:
            print("routing population ready: %d known external nodes" % known)
            return
        time.sleep(0.2)
    known = len(node.config.routing.knownExternalNodes())
    raise RuntimeError(
        "routing population timed out after %.1fs (%d known external nodes, "
        "wanted at least %d)" % (timeout, known, min_known)
    )

def runTests(host, port, listenport=None):
    ensureGatewayReachable(host, port)
    f1 = generateTestFile(5120)
    f2 = generateTestFile(5120)
    f3 = f2+".dup"
    shutil.copy(f2, f3)
    f4 = generateTestFile(513000)
    f5 = generateTestFile(513000)
    f6 = f5+".dup"
    shutil.copy(f5, f6)

    node = FludNode(port=listenport)
    if port == None:
        port = node.config.port
    node.run()
    node.connectViaGateway(host, port)
    waitForRoutingPopulation(node)

    d = doTests(node, [f1, f2], [f4, f5], [f2, f3], [f5, f6])
    d.addBoth(cleanup, node, [f1, f2, f3, f4, f5, f6])
    node.join()

if __name__ == '__main__':
    faulthandler.enable()
    faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)
    localhost = socket.getfqdn()
    if len(sys.argv) == 3: 
        runTests(sys.argv[1], eval(sys.argv[2])) # talk to [1] on port [2]
    elif len(sys.argv) == 4: 
        # talk to [1] on port [2], listen on port [3]
        runTests(sys.argv[1], eval(sys.argv[2]), eval(sys.argv[3]))
    else:
        print("must run this test against a flud network (no single node op)")
        print("usage: %s [<othernodehost othernodeport> |"\
                " <othernodehost othernodeport listenport>]" % sys.argv[0])
