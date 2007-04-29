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

def testerror(failure, message, node):
	"""
	error handler for test errbacks
	"""
	print "testerror message: %s" % message
	print "testerror: %s" % str(failure)
	print "At least 1 test FAILED"
	return failure

def checkDELETE(res, nKu, fname, fkey, node, host, port):
	""" checks to ensure the file was deleted """
	# XXX: check to see that its gone
	print "all tests PASSED"
	return res 

def testDELETE(res, nKu, fname, fkey, node, host, port):
	""" Tests sendDelete, and invokes checkDELETE on success """
	print "starting testDELETE"
	deferred = node.client.sendDelete(fkey, host, port, nKu)
	deferred.addCallback(checkDELETE, nKu, fname, fkey, node, host, port)
	deferred.addErrback(testerror, "failed at testDELETE", node)
	return deferred

def checkVERIFY(res, nKu, fname, fkey, node, host, port, hash):
	""" executes after testVERIFY """
	if long(hash, 16) != long(res, 16):
		raise failure.DefaultException("verify didn't match: %s != %s"
				% (hash, res))
	return testDELETE(res, nKu, fname, fkey, node, host, port)

def testVERIFY(nKu, fname, fkey, node, host, port):
	""" executes after checkRETRIEVE """
	""" Test sendVerify """
	print "starting testVERIFY"
	
	fd = os.open(fname, os.O_RDONLY)
	fsize = os.fstat(fd)[stat.ST_SIZE]
	length = 20
	offset = random.randrange(fsize-length)
	os.lseek(fd, offset, 0)
	data = os.read(fd, length)
	os.close(fd)
	hash = FludCrypto.hashstring(data)
	deferred = node.client.sendVerify(fkey, offset, length, host, port, nKu)
	deferred.addCallback(checkVERIFY, nKu, fname, fkey, node, host, port, hash)
	deferred.addErrback(testerror, "failed at testVERIFY", node)
	return deferred

def checkRETRIEVE(res, nKu, fname, fkey, node, host, port):
	""" Compares the file that was stored with the one that was retrieved """
	f1 = open(fname)
	f2 = open(os.path.join(node.config.clientdir, fkey))
	if (f1.read() != f2.read()):
		f1.close()
		f2.close()
		raise failure.DefaultException("upload/download files don't match")
	f1.close()
	f2.close()
	return testVERIFY(nKu, fname, fkey, node, host, port)

def testRETRIEVE(res, nKu, fname, fkey, node, host, port):
	""" Tests sendRetrieve, and invokes checkRETRIEVE on success """
	print "starting testRETRIEVE"
	deferred = node.client.sendRetrieve(fkey, host, port, nKu)
	deferred.addCallback(checkRETRIEVE, nKu, fname, fkey, node, host, port)
	deferred.addErrback(testerror, "failed at testRETRIEVE", node)
	return deferred

def testSTORE(nKu, fname, fkey, node, host, port):
	""" Tests sendStore, and invokes testRETRIEVE on success """
	print "starting testSTORE"
	deferred = node.client.sendStore(fname, host, port, nKu)
	deferred.addCallback(testRETRIEVE, nKu, fname, fkey, node, host, port)
	deferred.addErrback(testerror, "failed at testSTORE", node)
	return deferred

def testID(fname, fkey, node, host, port):
	""" Tests sendGetID(), and invokes testSTORE on success """
	print "starting testID"
	deferred = node.client.sendGetID(host, port)
	deferred.addCallback(testSTORE, fname, fkey, node, host, port)
	deferred.addErrback(testerror, "failed at testID", node)
	return deferred

	
def cleanup(_, node, filenamelist):
	for f in filenamelist:
		try:
			os.remove(f)
		except:
			print "couldn't remove %s" % f
	reactor.callLater(1, node.stop)

def generateTestData(minSize):
	fname = tempfile.mktemp()
	f = open(fname, 'w')
	data = FludCrypto.generateRandom(minSize/50)
	for i in range(0, 51+random.randrange(50)):
		f.write(data)
	f.close()
	filekey = FludCrypto.hashfile(fname)
	filekey = fencode(int(filekey, 16))
	filename = os.path.join("/tmp",filekey)
	os.rename(fname,filename)
	return (filename, filekey)

def runTests(host, port=None, listenport=None):
	(largeFilename, largeFilekey) = generateTestData(512000)
	node = FludNode(port=listenport)
	if port == None:
		port = node.config.port
	node.run()
	d = testID(largeFilename, largeFilekey, node, host, port)
	d.addBoth(cleanup, node, [largeFilename,])
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
