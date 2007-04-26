#!/usr/bin/python

import time, os, stat, random, sys, logging, socket
import FludCrypto
from FludNode import FludNode
from Protocol.FludClient import FludClient
from Protocol.FludCommUtil import *
from fencode import *
from twisted.python import failure
from twisted.internet import defer

"""
Test code for kprimitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""
# XXX: check return from ops to see if they passed (e.g., if STORE fails, we
#      are notified [currently] by the html page that is returned).

# XXX: should make a random file each time this is run...

CONCURRENT=50

node = None

testval = {'b': { 802484L: 465705L, 780638L: 465705L, 169688L: 465705L, 
267175L: 465705L, 648636L: 465705L, 838315L: 465705L, 477619L: 465705L, 
329906L: 465705L, 610565L: 465705L, 217811L: 465705L, 374124L: 465705L, 
357214L: 465705L, 147307L: 465705L, 427751L: 465705L, 927853L: 465705L, 
760369L: 465705L, 707029L: 465705L, 479234L: 465705L, 190455L: 465705L, 
647489L: 465705L, 620470L: 465705L, 777532L: 465705L, 622383L: 465705L, 
573283L: 465705L, 613082L: 465705L, 433593L: 465705L, 584543L: 465705L, 
337485L: 465705L, 911014L: 465705L, 594065L: 465705L, 375876L: 465705L, 
726818L: 465705L, 835759L: 465705L, 814060L: 465705L, 237176L: 465705L, 
538268L: 465705L, 272650L: 465705L, 314058L: 465705L, 257714L: 465705L, 
439931L: 465705L}, 
'm': {'meta': 'sMk-yXrPchYd416-55P2v_kZysNLvkkuEyD01CawjIP_5SRqoq8LR8UsRQdsX31XZMf67zKz-DePhXUrMeI3Mqbj6-bXbzkutAw9hHTueH6mxRrEXwQlk_1l2dDgsiGfAyWlN_3OyQkbEWNLD5NK_E7uV8ynqDOyNbvDWdIJ70_QY_5lKMOrRqNUOfpcji9AQcR99uw72Hfc_1lG464uUv4_Wc4PS77EjSHoDzYmWXheTS_gWeswJKj0MX1VEFn7YAHoSDCeLIAVjwxLrJfSKn_6C0-RCQN5ZfdUnYQg0NFIogxtPHpxorxpNDNs9hWOK46QbcS2b8z9ODA9JPFq94w==', 'eeK': 'sTTVTmNUXTmzUMqPVaSwhruXdTWCoC8Jo9zgNppRAhco4BfrX1gbz9njvCg3tQj7fuXS2OP-MrNqBYINSAfCnMuD9pdYGRGWyf8hsJJ4g2MBdUAqBAlK1iILMlWK0hL5Z4L2n2zZbIKB26bocsDy8akS5aK91KDgX5ubq7HkL4NE='}}

logger = logging.getLogger('test')
screenhandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s:'
		' %(message)s', datefmt='%H:%M:%S')
screenhandler.setFormatter(formatter)
logger.addHandler(screenhandler)
logger.setLevel(logging.DEBUG)

class ErrDeferredList(defer.DeferredList):
	"""
	NewDeferredList acts just like DeferredList, except that if
	*any* of the Deferreds in the DeferredList errback(), the NewDeferredList
	also errback()s.  This is different from DeferredList(fireOnOneErrback=True)
	in that if you use that method, you only know about the first failure,
	and you won't learn of subsequent failures/success in the list
	returnOne indicates whether the full result of the DeferredList should
	be returned, or just the first result (or first error)
	"""
	def __init__(self, list, returnOne=False):
		defer.DeferredList.__init__(self, list, consumeErrors=True)
		self.returnOne = returnOne
		self.addCallback(self.wrapResult)

	def wrapResult(self, result):
		#print "DEBUG: result= %s" % result
		for i in result:
			if i[0] == False:
				if self.returnOne:
					raise failure.DefaultException(i[1])
				else:
					raise failure.DefaultException(result)
		if self.returnOne:
			#print "DEBUG: returning %s" % str(result[0][1])
			return result[0][1]
		else:
			#print "DEBUG: returning %s" % result
			return result

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

def itersuccess(res, message):
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

	m = testval.pop('m')
	testval[node.config.Ku.id()] = m

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
		print "Warning: testing against self my result in timeout failures"
		runTests(localhost) # test by talking to self
	elif len(sys.argv) == 2:
		runTests(localhost, eval(sys.argv[1])) # talk to self on port [1]
	elif len(sys.argv) == 3: 
		runTests(sys.argv[1], eval(sys.argv[2])) # talk to [1] on port [2]
	elif len(sys.argv) == 4: 
		# talk to [1] on port [2], listen on port [3]
		runTests(sys.argv[1], eval(sys.argv[2]), eval(sys.argv[3]))
