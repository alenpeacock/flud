#!/usr/bin/env python3

import time, os, stat, random, sys, logging, socket
from twisted.python import failure

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from flud.FludNode import FludNode
from flud.protocol.FludClient import FludClient
from flud.protocol.FludCommUtil import *
from flud.fencode import fencode, fdecode

"""
Test code for primitive DHT operations. 
"""

stay_alive = 1
filename = "/tmp/tempstoredata"
filekey = os.path.basename(filename)
key = 87328673569979667228965797330646992089697345905484734072690869757741450870337

# format of block metadata is 
# {(i, datakey): storingNodeID, ..., 'n': n, 'm': m} 
# where i<n+m, datakey is a sha256 of the data stored, and storingNodeID is
# either a nodeID or a list of nodeIDs.
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
#logger.setLevel(logging.DEBUG)
logger.setLevel(logging.INFO)

def cleanup(_, node):
    logger.info("waiting %ds to shutdown..." % stay_alive)
    reactor.callLater(stay_alive, node.stop)

def testerror(failure, message, node):
    """
    error handler for test errbacks
    """
    logger.warn("testerror message: %s" % message)
    logger.warn("testerror: '%s'" % str(failure))
    logger.warn("At least 1 test FAILED")

def endtests(res, nKu, node, host, port):
    """ executes after all tests """
    try:
        res = fdecode(res)
    except ValueError:
        pass
    if res != testval:
        return testerror(None, "retrieved value does not match stored value:"
                " '%s' != '%s'" % (res, testval), node)
    
    logger.info("testkFindVal PASSED")
    logger.debug("testkFindVal result: %s" % str(res))

    logger.info("all tests PASSED")
    return res

def testkFindVal(res, nKu, node, host, port):
    logger.info("testSendkFindVal PASSED")
    logger.debug("testSendkFindVal result: %s" % str(res))
    
    logger.info("attempting testkFindValue")
    deferred = node.client.kFindValue(key)
    deferred.addCallback(endtests, nKu, node, host, port)
    deferred.addErrback(testerror, "failed at testkFindValue", node)
    return deferred

def testSendkFindVal(res, nKu, node, host, port):
    logger.info("testkStore PASSED")
    logger.debug("testkStore result: %s" % str(res))
    
    logger.info("attempting testSendkFindValue")
    deferred = node.client.sendkFindValue(host, port, key)
    deferred.addCallback(testkFindVal, nKu, node, host, port)
    deferred.addErrback(testerror, "failed at testSendkFindValue", node)
    return deferred

def testkStore(res, nKu, node, host, port):
    logger.info("testSendkStore PASSED")
    logger.debug("testSendkStore result: %s" % str(res))

    logger.info("attempting testkStore")
    deferred = node.client.kStore(key, testval)
    deferred.addCallback(testSendkFindVal, nKu, node, host, port)
    deferred.addErrback(testerror, "failed at testkStore", node)
    return deferred

def testSendkStore(res, nKu, node, host, port):
    logger.info("testkFindNode PASSED")
    logger.debug("testkFindNode result: %s" % str(res))

    logger.info("attempting testSendkStore")
    deferred = node.client.sendkStore(host, port, key, testval)
    deferred.addCallback(testkStore, nKu, node, host, port)
    deferred.addErrback(testerror, "failed at testkStore", node)
    return deferred

def testkFindNode(res, nKu, node, host, port):
    """ executes after testSendkFindNode """
    logger.info("testSendkFindNode PASSED")
    logger.debug("testSendkFindNode result: %s" % str(res))
    
    logger.info("attempting kFindNode")
    deferred = node.client.kFindNode(key)
    deferred.addCallback(testSendkStore, nKu, node, host, port)
    deferred.addErrback(testerror, "failed at kFindNode", node)
    return deferred

def testSendkFindNode(nKu, node, host, port):
    """ executes after testGetID """
    logger.info("testkGetID PASSED")
    
    logger.info("attempting sendkFindNode")
    deferred = node.client.sendkFindNode(host, port, key)
    deferred.addCallback(testkFindNode, nKu, node, host, port)
    deferred.addErrback(testerror, "failed at sendkFindNode", node)
    return deferred

def testGetID(node, host, port):
    """ Tests sendGetID(), and invokes testSendkFindNode on success """

    deferred = node.client.sendGetID(host, port)
    deferred.addCallback(testSendkFindNode, node, host, port)
    deferred.addErrback(testerror, "failed at testGetID", node)
    return deferred
    
def runTests(host, port=None, listenport=None):
    host = getCanonicalIP(host)
    node = FludNode(port=listenport)
    if port == None:
        port = node.config.port
    logger.info("testing against %s:%s, localport=%s" % (host, 
        port, listenport))
    node.run()
    d = testGetID(node, host, port)
    d.addBoth(cleanup, node)
    #testkFindVal("blah", node.config.Ku, node, host, port)
    node.join()

"""
Main currently invokes test code
"""
if __name__ == '__main__':
    localhost = socket.getfqdn()
    if len(sys.argv) == 1:
        runTests(localhost) # test by talking to self
    elif len(sys.argv) == 2:
        runTests(localhost, eval(sys.argv[1]))
    elif len(sys.argv) == 3: 
        runTests(sys.argv[1], eval(sys.argv[2]))
    elif len(sys.argv) == 4: 
        runTests(sys.argv[1], eval(sys.argv[2]), eval(sys.argv[3]))
