#!/usr/bin/python

from FludNode import FludNode
from Protocol.FludClient import FludClient
import FludCrypto
from Protocol.FludCommUtil import *
import time, os, stat, random, sys, logging, socket, tempfile
from twisted.python import failure
from fencode import fencode

"""
Test code for primitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""

filename = ""
filekey = ""

def testerror(failure, message, node):
	"""
	error handler for test errbacks
	"""
	print "testerror message: %s" % message
	print "testerror: %s" % str(failure)
	print "At least 1 test FAILED"
	return failure

def checkDELETE(res, nKu, node, host, port):
	""" checks to ensure the file was deleted """
	# XXX: check to see that its gone
	print "all tests PASSED"
	return res 

def testDELETE(res, nKu, node, host, port):
	""" Tests sendDelete, and invokes checkDELETE on success """
	print "starting testDELETE"
	deferred = node.client.sendDelete(filekey, host, port, nKu)
	deferred.addCallback(checkDELETE, nKu, node, host, port)
	deferred.addErrback(testerror, "failed at testDELETE", node)
	return deferred

def checkVERIFY(res, nKu, node, host, port, hash):
	""" executes after testVERIFY """
	if long(hash, 16) != long(res, 16):
		raise failure.DefaultException("verify didn't match: %s != %s"
				% (hash, res))
		#return testDELETE(res, nKu, node, host, port)

def testVERIFY(nKu, node, host, port):
	""" executes after checkRETRIEVE """
	""" Test sendVerify """
	print "starting testVERIFY"
	
	fd = os.open(filename, os.O_RDONLY)
	fsize = os.fstat(fd)[stat.ST_SIZE]
	length = 20
	offset = random.randrange(fsize-length)
	os.lseek(fd, offset, 0)
	data = os.read(fd, length)
	os.close(fd)
	hash = FludCrypto.hashstring(data)
	deferred = node.client.sendVerify(filekey, offset, length, host, port, nKu)
	deferred.addCallback(checkVERIFY, nKu, node, host, port, hash)
	deferred.addErrback(testerror, "failed at testVERIFY", node)
	return deferred

def checkRETRIEVE(res, nKu, node, host, port):
	""" Compares the file that was stored with the one that was retrieved """
	f1 = open(filename)
	f2 = open(os.path.join(node.config.clientdir,filekey))
	if (f1.read() != f2.read()):
		f1.close()
		f2.close()
		raise failure.DefaultException("upload/download files don't match")
	f1.close()
	f2.close()
	return testVERIFY(nKu, node, host, port)

def testRETRIEVE(res, nKu, node, host, port):
	""" Tests sendRetrieve, and invokes checkRETRIEVE on success """
	print "starting testRETRIEVE"
	deferred = node.client.sendRetrieve(filekey, host, port, nKu)
	deferred.addCallback(checkRETRIEVE, nKu, node, host, port)
	deferred.addErrback(testerror, "failed at testRETRIEVE", node)
	return deferred

def testSTORE(nKu, node, host, port):
	""" Tests sendStore, and invokes testRETRIEVE on success """
	print "starting testSTORE"
	deferred = node.client.sendStore(filename, host, port, nKu)
	deferred.addCallback(testRETRIEVE, nKu, node, host, port)
	deferred.addErrback(testerror, "failed at testSTORE", node)
	return deferred

def testID(node, host, port):
	""" Tests sendGetID(), and invokes testSTORE on success """
	print "starting testID"
	deferred = node.client.sendGetID(host, port)
	deferred.addCallback(testSTORE, node, host, port)
	deferred.addErrback(testerror, "failed at testID", node)
	return deferred

	
def cleanup(_, node):
	os.remove(filename)
	reactor.callLater(1, node.stop)

def generateTestData():
	global filename
	global filekey
	fname = tempfile.mktemp()
	f = open(fname, 'w')
	for i in range(0, random.randrange(10)+1):
		f.write(FludCrypto.generateRandom(1024))
	f.close()
	filekey = FludCrypto.hashfile(fname)
	filekey = fencode(int(filekey, 16))
	filename = os.path.join("/tmp",filekey)
	os.rename(fname,filename)

def runTests(host, port=None, listenport=None):
	generateTestData()
	node = FludNode(port=listenport)
	if port == None:
		port = node.config.port
	node.run()
	d = testID(node, host, port)
	d.addBoth(cleanup, node)
	node.join()

"""
Main currently invokes test code
"""
if __name__ == '__main__':
	localhost = socket.getfqdn()
	if len(sys.argv) == 1:
		runTests(localhost) # test by talking to self
	elif len(sys.argv) == 2:
		runTests(localhost, eval(sys.argv[1])) # talk to self on port [1]
	elif len(sys.argv) == 3: 
		runTests(sys.argv[1], eval(sys.argv[2])) # talk to [1] on port [2]
	elif len(sys.argv) == 4: 
		# talk to [1] on port [2], listen on port [3]
		runTests(sys.argv[1], eval(sys.argv[2]), eval(sys.argv[3]))
