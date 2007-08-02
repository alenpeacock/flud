#!/usr/bin/python

from FludNode import FludNode
from Protocol.FludClient import FludClient
import FludCrypto
from Protocol.FludCommUtil import *
import time, os, stat, random, sys, logging, socket, tempfile
from twisted.python import failure
from fencode import *
from StringIO import StringIO
from zlib import crc32
from FludDefer import ErrDeferredList

"""
Test code for primitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""

# metadatablock: (block#,n,k,blockdata)
metadatablock = fencode((1,20,40,'adfdsfdffffffddddddddddddddd'))

def testerror(failure, message, node):
	"""
	error handler for test errbacks
	"""
	print "testerror message: %s" % message
	print "testerror: %s" % str(failure)
	print "At least 1 test FAILED"
	return failure

def allGood(_, nKu):
	print "all tests PASSED"
	return nKu 

def checkDELETE(res, nKu, fname, fkey, mkey, node, host, port):
	""" checks to ensure the file was deleted """
	# XXX: check to see that its gone
	return allGood(res, nKu)

def testDELETE(res, nKu, fname, fkey, mkey, node, host, port):
	""" Tests sendDelete, and invokes checkDELETE on success """
	print "starting testDELETE %s" % fname
	deferred = node.client.sendDelete(fkey, mkey, host, port, nKu)
	deferred.addCallback(checkDELETE, nKu, fname, fkey, mkey, node, host, port)
	deferred.addErrback(testerror, "failed at testDELETE", node)
	return deferred
	#return checkDELETE(None, nKu, fname, fkey, node, host, port)

def checkVERIFY(res, nKu, fname, fkey, mkey, node, host, port, hash):
	""" executes after testVERIFY """
	if long(hash, 16) != long(res, 16):
		raise failure.DefaultException("verify didn't match: %s != %s"
				% (hash, res))
	return testDELETE(res, nKu, fname, fkey, mkey, node, host, port)

def testVERIFY(nKu, fname, fkey, mkey, node, host, port):
	""" executes after checkRETRIEVE """
	""" Test sendVerify """
	print "starting testVERIFY %s" % fname
	
	fd = os.open(fname, os.O_RDONLY)
	fsize = os.fstat(fd)[stat.ST_SIZE]
	length = 20
	offset = random.randrange(fsize-length)
	os.lseek(fd, offset, 0)
	data = os.read(fd, length)
	os.close(fd)
	hash = FludCrypto.hashstring(data)
	mkey = crc32(fname)
	deferred = node.client.sendVerify(fkey, offset, length, host, port, nKu,
			(mkey, StringIO(metadatablock)))
	deferred.addCallback(checkVERIFY, nKu, fname, fkey, mkey, node, host, port,
			hash)
	deferred.addErrback(testerror, "failed at testVERIFY", node)
	return deferred

def checkRETRIEVE(res, nKu, fname, fkey, mkey, node, host, port):
	""" Compares the file that was stored with the one that was retrieved """
	f1 = open(fname)
	f2 = open(res[1]) # XXX: don't rely on position, find the one without .meta
	if (f1.read() != f2.read()):
		f1.close()
		f2.close()
		raise failure.DefaultException(
				"upload/download (%s, %s) files don't match" % (fname, 
					os.path.join(node.config.clientdir, fkey)))
	print "%s (%d) and %s (%d) match" % (fname, os.stat(fname)[stat.ST_SIZE],
		res[1], os.stat(res[1])[stat.ST_SIZE])
	f1.close()
	f2.close()
	# make sure the metadata is the same...
	mkey = crc32(fname)
	f3 = open(res[0]) # XXX: ... and the one with .meta
	md = f3.read()
	if md != metadatablock:
		raise failure.DefaultException("upload/download metadata doesn't match"
				" (%s != %s)" % (md, metadatablock))
	return testVERIFY(nKu, fname, fkey, mkey, node, host, port)

def testRETRIEVE(res, nKu, fname, fkey, mkey, node, host, port):
	""" Tests sendRetrieve, and invokes checkRETRIEVE on success """
	print "starting testRETRIEVE %s" % fname
	mkey = crc32(fname)
	deferred = node.client.sendRetrieve(fkey, host, port, nKu, mkey)
	deferred.addCallback(checkRETRIEVE, nKu, fname, fkey, mkey, node, host, 
			port)
	deferred.addErrback(testerror, "failed at testRETRIEVE", node)
	return deferred

def testSTORE(nKu, fname, fkey, node, host, port):
	""" Tests sendStore, and invokes testRETRIEVE on success """
	mkey = crc32(fname)
	print "starting testSTORE %s (%s)" % (fname, mkey)
	deferred = node.client.sendStore(fname, (mkey, StringIO(metadatablock)), 
			host, port, nKu)
	deferred.addCallback(testRETRIEVE, nKu, fname, fkey, mkey, node, host, port)
	deferred.addErrback(testerror, "failed at testSTORE", node)
	return deferred

def testID(node, host, port):
	""" Tests sendGetID(), and invokes testSTORE on success """
	print "starting testID"
	deferred = node.client.sendGetID(host, port)
	deferred.addErrback(testerror, "failed at testID", node)
	return deferred

def testAggSTORE(nKu, aggFiles, node, host, port):
	print "starting testAggSTORE"
	dlist = []
	for i in aggFiles:
		mkey = crc32(i[0]) 
		print "testAggSTORE %s (%s)" % (i[0], mkey)
		deferred = node.client.sendStore(i[0], (mkey, StringIO(metadatablock)),
				host, port, nKu)
		deferred.addCallback(testRETRIEVE, nKu, i[0], i[1], mkey, node, host, 
				port)
		deferred.addErrback(testerror, "failed at testAggSTORE", node)
		dlist.append(deferred)
	dl = ErrDeferredList(dlist)
	dl.addCallback(allGood, nKu)
	dl.addErrback(testerror, "failed at testAggSTORE", node)
	return dl


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
	(smallFilename, smallFilekey) = generateTestData(5120)
	aggFiles = []
	for i in range(4):
		aggFiles.append(generateTestData(4096))
	node = FludNode(port=listenport)
	if port == None:
		port = node.config.port
	node.run()
	d = testID(node, host, port)
	d.addCallback(testSTORE, largeFilename, largeFilekey, node, host, port)
	d.addCallback(testSTORE, smallFilename, smallFilekey, node, host, port)
	d.addCallback(testAggSTORE, aggFiles, node, host, port)
	d.addBoth(cleanup, node, [i[0] for i in aggFiles] + [largeFilename, 
		smallFilename])
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
