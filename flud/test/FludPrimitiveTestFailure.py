#!/usr/bin/python

import time, os, stat, random, sys, logging, socket, shutil, tempfile
from binascii import crc32
from StringIO import StringIO
from twisted.python import failure

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
	os.path.abspath(__file__)))))
from flud.FludNode import FludNode
from flud.protocol.FludClient import FludClient
from flud.FludCrypto import generateRandom, hashfile
from flud.protocol.FludCommUtil import *
from flud.fencode import fencode

"""
Test code for primitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""

smallfilekey = ""
smallfilename = ""
smallfilenamebad = ""

largefilekey = ""
largefilename = ""
largefilenamebad = ""

metadata = 'aaaa'

def testerror(failure, message, node):
	"""
	error handler for test errbacks
	"""
	print "testerror message: %s" % message
	print "testerror: %s" % str(failure)
	print "At least 1 test FAILED"
	raise failure

def testUnexpectedSuccess(res, message, node):
	print "unexpected success message: %s" % message
	print "At least 1 test succeeded when it should have failed"
	raise "bad"

def testDELETEBadKeyFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.BadRequestException'):
		print "%s" % msg
		# the end
	else:
		# XXX: here and elsewhere, raise something more descriptive, otherwise
		# its waay confusing
		print "the following trace may be misleading..."
		raise failure

def testDELETEBadKey(nKu, node, host, port):
	print "starting testDELETEBadKey"
	path = os.path.join("somedir", largefilekey)
	deferred = node.client.sendDelete(path, crc32(path), host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, "DELETE with bad key succeeded",
			node)
	deferred.addErrback(testDELETEBadKeyFailed, 
			"DELETE with bad key failed as expected", node, nKu, host, port)
	return deferred

def testVERIFYBadKeyFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.NotFoundException'):
		print "%s" % msg
		return testDELETEBadKey(nKu, node, host, port)
	else:
		raise failure

def testVERIFYBadKey(nKu, node, host, port):
	print "starting testVERIFYBadKey"
	fsize = os.stat(smallfilename)[stat.ST_SIZE]
	offset = fsize-20
	deferred = node.client.sendVerify(smallfilenamebad, offset, 5, host, 
			port, nKu)
	deferred.addCallback(testUnexpectedSuccess, 
			"verified file with bad key succeeded", node)
	deferred.addErrback(testVERIFYBadKeyFailed, 
			"VERIFY of bad filekey failed as expected", node, nKu, host, port)
	return deferred

def testVERIFYBadLengthFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.BadRequestException'):
		print "%s" % msg
		return testVERIFYBadKey(nKu, node, host, port)
	else:
		raise failure

def testVERIFYBadLength(nKu, node, host, port):
	print "starting testVERIFYBadOffset"
	fsize = os.stat(smallfilename)[stat.ST_SIZE]
	offset = fsize-10
	deferred = node.client.sendVerify(smallfilekey, offset, 20, host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, "verified file with bad length",
			node)
	deferred.addErrback(testVERIFYBadLengthFailed, 
			"VERIFY of bad length failed as expected", node, nKu, host, port)
	return deferred

def testVERIFYBadOffsetFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.BadRequestException'):
		print "%s" % msg
		return testVERIFYBadLength(nKu, node, host, port)
	else:
		print "VERIFYBadOffset failed as expected, but with wrong failure"
		raise failure

def testVERIFYBadOffset(nKu, node, host, port):
	print "starting testVERIFYBadOffset"
	fsize = os.stat(smallfilename)[stat.ST_SIZE]
	offset = fsize+2
	deferred = node.client.sendVerify(smallfilekey, offset, 20, host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, "verified file with bad offset",
			node)
	deferred.addErrback(testVERIFYBadOffsetFailed, 
			"VERIFY of bad offset failed as expected", node, nKu, host, port)
	return deferred

def testVERIFYNotFoundFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.NotFoundException'):
		print "%s" % msg
		return testVERIFYBadOffset(nKu, node, host, port)
	else:
		raise failure

def testVERIFYNotFound(nKu, node, host, port):
	print "starting testVERIFYNotFound"
	deferred = node.client.sendVerify(largefilekey, 10, 10, host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, "verified non-existent file",
			node)
	deferred.addErrback(testVERIFYNotFoundFailed, 
			"VERIFY of non-existent file failed as expected", node, nKu,
			host, port)
	return deferred

def testRETRIEVEIllegalPathFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.BadRequestException'):
		print "%s" % msg
		return testVERIFYNotFound(nKu, node, host, port)
	else:
		raise failure

def testRETRIEVEIllegalPath(nKu, node, host, port):
	print "starting testRETRIEVEIllegalPath"
	deferred = node.client.sendRetrieve(os.path.join("somedir",smallfilekey), 
			host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, 
			"retrieved file with illegal path", node)
	deferred.addErrback(testRETRIEVEIllegalPathFailed, 
			"RETRIEVE using illegal path failed as expected", node, nKu, 
			host, port)
	return deferred

def testRETRIEVENotFoundFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.NotFoundException'):
		print "%s" % msg
		return testRETRIEVEIllegalPath(nKu, node, host, port)
	else:
		raise failure

def testRETRIEVENotFound(nKu, node, host, port):
	print "starting testRETRIEVENotFound"
	deferred = node.client.sendRetrieve(largefilekey, host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, 
			"retrieved file that shouldn't exist", node)
	deferred.addErrback(testRETRIEVENotFoundFailed, 
			"RETRIEVE of non-existent file failed as expected", node, nKu,
			host, port)
	return deferred

def testSTORELargeFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.BadCASKeyException'):
		print "%s" % msg
		return testRETRIEVENotFound(nKu, node, host, port)
	else:
		raise failure

def testSTOREBadKeyLarge(nKu, node, host, port):
	print "starting testSTOREBadKeyLarge"
	deferred = node.client.sendStore(largefilenamebad, 
			(crc32(largefilenamebad), StringIO(metadata)), host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, "large file, bad key succeeded",
			node)
	deferred.addErrback(testSTORELargeFailed, 
			"large STORE with bad key failed as expected", node, nKu, 
			host, port)
	return deferred

def testSTORESmallFailed(failure, msg, node, nKu, host, port):
	if failure.check('protocol.FludCommUtil.BadCASKeyException'):
		print "%s" % msg
		return testSTOREBadKeyLarge(nKu, node, host, port)
	else:
		raise failure


def testSTOREBadKeySmall(nKu, node, host, port):
	print "starting testSTOREBadKeySmall"
	deferred = node.client.sendStore(smallfilenamebad, 
			(crc32(smallfilenamebad), StringIO(metadata)), host, port, nKu)
	deferred.addCallback(testUnexpectedSuccess, "small file, bad key succeeded",
			node)
	deferred.addErrback(testSTORESmallFailed, 
			"small STORE with bad key failed as expected", node, nKu, 
			host, port)
	return deferred

def testSTORESuccess(res, nKu, node, host, port):
	print "testSTORE succeeded: %s" % res
	return testSTOREBadKeySmall(nKu, node, host, port)

def testSTORE(nKu, node, host, port):
	# store a file successfully for later failure tests (VERIFY, etc)
	print "starting testSTORE"
	deferred = node.client.sendStore(smallfilename, 
			(crc32(smallfilename), StringIO(metadata)), host, port, nKu)
	deferred.addCallback(testSTORESuccess, nKu, node, host, port)
	deferred.addErrback(testerror, "failed at testSTORE", node)
	return deferred

# XXX: need to test bogus headers for all commands (BAD_REQUEST)
# XXX: need to test failures for authentication 

def testID(node, host, port):
	""" Tests sendGetID(), and invokes testSTORE on success """
	print "starting testID"
	deferred = node.client.sendGetID(host, port)
	deferred.addCallback(testSTORE, node, host, port)
	#deferred.addCallback(testSTOREBadKeySmall, node, host, port)
	deferred.addErrback(testerror, "failed at testID", node)
	return deferred

	
def cleanup(err, node):
	if err:
		print "cleaning up: %s" % err
	else:
		print "cleaning up"
	os.remove(smallfilename)
	os.remove(smallfilenamebad)
	os.remove(largefilename)
	os.remove(largefilenamebad)
	reactor.callLater(1, node.stop)

def generateTestData():
	def generateFiles(minsize):
		fname = tempfile.mktemp()
		f = open(fname, 'w')
		f.write('\0'*minsize)
		f.write(generateRandom(random.randrange(256)+1))
		f.close()
		filekey = hashfile(fname)
		filekey = fencode(int(filekey, 16))
		filename = os.path.join("/tmp",filekey)
		os.rename(fname,filename)
		filenamebad = os.path.join("/tmp/","bad"+filekey[3:])
		shutil.copy(filename, filenamebad)
		return (filekey, filename, filenamebad)

	global smallfilekey
	global smallfilename
	global smallfilenamebad
	(smallfilekey, smallfilename, smallfilenamebad) = generateFiles(1024)

	global largefilekey
	global largefilename
	global largefilenamebad
	(largefilekey, largefilename, largefilenamebad) = generateFiles(512000)

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
