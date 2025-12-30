#!/usr/bin/env python3

import time, os, stat, random, sys, logging, socket
from twisted.python import failure
from twisted.internet import defer

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from flud.FludNode import FludNode
from flud.protocol.FludClient import FludClient
from flud.protocol.FludCommUtil import *
from flud.fencode import *
from flud.FludDefer import ErrDeferredList

"""
Test code for kprimitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""
# XXX: check return from ops to see if they passed (e.g., if STORE fails, we
#      are notified [currently] by the html page that is returned).

# XXX: should make a random file each time this is run...

CONCURRENT=50
CONCREPORT=10

node = None

# format of block metadata is 
# {(i, datakey): storingNodeID, ..., 'n': n, 'm': m} 
# where i<n+m, datakey is a sha256 of the data stored, and storingNodeID is
# either a nodeID or a list of nodeIDs
testval = {(0, 802484): 465705, (1, 780638): 465705, (2, 169688): 465705,
        (3, 267175): 465705, (4, 648636): 465705, (5, 838315): 465705, 
        (6, 477619): 465705, (7, 329906): 465705, (8, 610565): 465705, 
        (9, 217811): 465705, (10, 374124): 465705, (11, 357214): 465705, 
        (12, 147307): 465705, (13, 427751): 465705, (14, 927853): 465705, 
        (15, 760369): 465705, (16, 707029): 465705, (17, 479234): 465705, 
        (18, 190455): 465705, (19, 647489): 465705, (20, 620470): 465705, 
        (21, 777532): 465705, (22, 622383): 465705, (23, 573283): 465705, 
        (24, 613082): 465705, (25, 433593): 465705, (26, 584543): 465705, 
        (27, 337485): 465705, (28, 911014): 465705, (29, 594065): 465705, 
        (30, 375876): 465705, (31, 726818): 465705, (32, 835759): 465705, 
        (33, 814060): 465705, (34, 237176): 465705, (35, 538268): 465705, 
        (36, 272650): 465705, (37, 314058): 465705, (38, 257714): 465705, 
        (39, 439931): 465705, 'k': 20, 'n': 20}

logger = logging.getLogger('test')
screenhandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s:'
        ' %(message)s', datefmt='%H:%M:%S')
screenhandler.setFormatter(formatter)
logger.addHandler(screenhandler)
logger.setLevel(logging.DEBUG)

def suitesuccess(results):
    logger.info("all tests in suite passed")
    #print results
    return results

def suiteerror(failure):
    logger.info("suite did not complete")
    logger.info("DEBUG: %s" % failure)
    return failure

def stagesuccess(result, message):
    logger.info("stage %s succeeded" % message)
    return result

def stageerror(failure, message):
    logger.info("stage %s failed" % message)
    #logger.info("DEBUG: %s" % failure)
    return failure

def itersuccess(res, i, message):
    if i % CONCREPORT == 0:
        logger.info("itersuccess: %s" % message)
    return res

def itererror(failure, message):
    logger.info("itererror message: %s" % message)
    #logger.info("DEBUG: %s" % failure)
    #logger.info("DEBUG: %s" % dir(failure)
    failure.printTraceback()
    return failure

def endtests(res, nKu, node, host, port):
    """ executes after all tests """
    try:
        res = fdecode(res)
    except ValueError:
        pass
    if res != testval:
        return failure.DefaultException("retrieved value does not match" 
                " stored value: '%s' != '%s'" % (res, testval))
    
    logger.log(logging.INFO,"testkFindVal PASSED: %s\n" % str(res))

    logger.log(logging.INFO,"all tests PASSED")
    return res

def testkFindVal(res, nKu, node, host, port, num=CONCURRENT):
    logger.log(logging.INFO,"testSendkFindVal PASSED: %s\n" % str(res))
    logger.log(logging.INFO,"attempting testkFindValue")
    dlist = []
    for i in range(num):
        key = random.randrange(2**256)
        deferred = node.client.kFindValue(key)
        deferred.addErrback(itererror, "kFindValue")
        dlist.append(deferred)
    d = ErrDeferredList(dlist, returnOne=True)
    d.addCallback(stagesuccess, "kFindValue")
    d.addErrback(stageerror, 'kFindValue')
    d.addCallback(endtests, nKu, node, host, port)
    return d

def testSendkFindVal(res, nKu, node, host, port, num=CONCURRENT):
    logger.log(logging.INFO, "testkStore PASSED: %s\n" % str(res))
    logger.log(logging.INFO, "attempting testSendkFindValue")
    dlist = []
    for i in range(num):
        key = random.randrange(2**256)
        deferred = node.client.sendkFindValue(host, port, key)
        deferred.addErrback(itererror, "sendkFindValue")
        dlist.append(deferred)
    d = ErrDeferredList(dlist, returnOne=True)
    d.addCallback(stagesuccess, "sendkFindValue")
    d.addErrback(stageerror, 'sendkFindValue')
    d.addCallback(testkFindVal, nKu, node, host, port, num)
    return d

def testkStore(res, nKu, node, host, port, num=CONCURRENT):
    logger.log(logging.INFO, "testSendkStore PASSED: %s" % str(res))
    logger.log(logging.INFO, "attempting testkStore")
    dlist = []
    for i in range(num):
        key = random.randrange(2**256)
        deferred = node.client.kStore(key, testval)
        deferred.addErrback(itererror, "kStore")
        dlist.append(deferred)
    d = ErrDeferredList(dlist, returnOne=True)
    d.addCallback(stagesuccess, "kStore")
    d.addErrback(stageerror, 'kStore')
    d.addCallback(testSendkFindVal, nKu, node, host, port, num)
    return d

def testSendkStore(res, nKu, node, host, port, num=CONCURRENT):
    logger.log(logging.INFO, "testkFindNode PASSED: %s" % str(res))
    logger.log(logging.INFO, "attempting testSendkStore")
    dlist = []
    for i in range(num):
        key = random.randrange(2**256)
        deferred = node.client.sendkStore(host, port, key, testval)
        deferred.addErrback(itererror, "sendkStore")
        dlist.append(deferred)
    d = ErrDeferredList(dlist, returnOne=True)
    d.addCallback(stagesuccess, "sendkStore")
    d.addErrback(stageerror, 'sendkStore')
    d.addCallback(testkStore, nKu, node, host, port, num)
    return d

def testkFindNode(res, nKu, node, host, port, num=CONCURRENT):
    logger.log(logging.INFO, "testSendkFindNode PASSED: %s" % str(res))
    logger.log(logging.INFO, "attempting kFindNode")
    dlist = []
    for i in range(num):
        key = random.randrange(2**256)
        deferred = node.client.kFindNode(key)
        deferred.addErrback(itererror, "kFindNode")
        dlist.append(deferred)
    d = ErrDeferredList(dlist, returnOne=True)
    d.addCallback(stagesuccess, "kFindNode")
    d.addErrback(stageerror, 'kFindNode')
    d.addCallback(testSendkStore, nKu, node, host, port, num)
    return d

def testSendkFindNode(nKu, node, host, port, num=CONCURRENT):
    logger.log(logging.INFO, "testkGetID PASSED")
    logger.log(logging.INFO, "attempting sendkFindNode")
    dlist = []
    for i in range(num):
        key = random.randrange(2**256)
        deferred = node.client.sendkFindNode(host, port, key)
        deferred.addErrback(itererror, "sendkFindNode")
        dlist.append(deferred)
    d = ErrDeferredList(dlist, returnOne=True)
    d.addCallback(stagesuccess, "sendkFindNode")
    d.addErrback(stageerror, 'sendkFindNode')
    d.addCallback(testkFindNode, nKu, node, host, port, num)
    return d

def testGetID(node, host, port, num=CONCURRENT):
    """ Tests sendGetID(), and invokes testSendkFindNode on success """
    deferred = node.client.sendGetID(host, port)
    deferred.addCallback(testSendkFindNode, node, host, port, num)
    deferred.addErrback(stageerror, "testGetID")
    return deferred
    
def runTests(host, port=None, listenport=None):
    num = CONCURRENT
    #num = 5
    node = FludNode(port=listenport)
    if port == None:
        port = node.config.port
    node.run()

    d = testGetID(node, host, port, CONCURRENT)
    d.addCallback(suitesuccess)
    d.addErrback(suiteerror)
    d.addBoth(cleanup, node)

    node.join()
    #node.start()  # doesn't work, because reactor may not have started 
                   # listening by time requests start flying


def cleanup(_, node):
    logger.info("shutting down in 1 seconds...")
    time.sleep(1)
    reactor.callLater(1, node.stop)
    logger.info("done cleaning up")

"""
Main currently invokes test code
"""
if __name__ == '__main__':
    localhost = socket.getfqdn()
    if len(sys.argv) == 1:
        print("Warning: testing against self may result in timeout failures")
        runTests(localhost) # test by talking to self
    elif len(sys.argv) == 2:
        runTests(localhost, eval(sys.argv[1])) # talk to self on port [1]
    elif len(sys.argv) == 3: 
        runTests(sys.argv[1], eval(sys.argv[2])) # talk to [1] on port [2]
    elif len(sys.argv) == 4: 
        # talk to [1] on port [2], listen on port [3]
        runTests(sys.argv[1], eval(sys.argv[2]), eval(sys.argv[3]))
