#!/usr/bin/python

from FludNode import FludNode
from Protocol.FludClient import FludClient
import FludCrypto
from Protocol.FludCommUtil import *
import time, os, stat, random, sys, logging, socket
from twisted.python import failure
from fencode import *

"""
Test code for primitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""

stay_alive = 1
filename = "/tmp/tempstoredata"
filekey = os.path.basename(filename)
key = 87328673569979667228965797330646992089697345905484734072690869757741450870337L
testval = { 802484L: 465705L, 780638L: 465705L, 169688L: 465705L, 
267175L: 465705L, 648636L: 465705L, 838315L: 465705L, 477619L: 465705L, 
329906L: 465705L, 610565L: 465705L, 217811L: 465705L, 374124L: 465705L, 
357214L: 465705L, 147307L: 465705L, 427751L: 465705L, 927853L: 465705L, 
760369L: 465705L, 707029L: 465705L, 479234L: 465705L, 190455L: 465705L, 
647489L: 465705L, 620470L: 465705L, 777532L: 465705L, 622383L: 465705L, 
573283L: 465705L, 613082L: 465705L, 433593L: 465705L, 584543L: 465705L, 
337485L: 465705L, 911014L: 465705L, 594065L: 465705L, 375876L: 465705L, 
726818L: 465705L, 835759L: 465705L, 814060L: 465705L, 237176L: 465705L, 
538268L: 465705L, 272650L: 465705L, 314058L: 465705L, 257714L: 465705L, 
439931L: 465705L}

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
