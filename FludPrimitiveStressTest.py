#!/usr/bin/python

import time, os, stat, random, sys, logging, socket
import FludCrypto
from FludNode import FludNode
from protocol.FludClient import FludClient
from protocol.FludCommUtil import *
from twisted.python import failure
from twisted.internet import defer
from fencode import *
from FludDefer import ErrDeferredList

"""
Test code for primitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""

CONCURRENT=300

node = None
files = None

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

def itersuccess(res, message):
	logger.info("itersuccess: %s" % message)
	return res

def itererror(failure, message):
	logger.info("itererror message: %s" % message)
	#logger.info("DEBUG: %s" % failure)
	#logger.info("DEBUG: %s" % dir(failure)
	failure.printTraceback()
	return failure

def checkVERIFY(results, nKu, host, port, hashes, num=CONCURRENT):
	logger.info("  checking VERIFY results...")
	for i in range(num):
		hash = hashes[i]
		res = results[i][1]
		if long(hash, 16) != long(res, 16):
			raise failure.DefaultException("verify didn't match: %s != %s"
					% (hash, res))
	logger.info("  ...VERIFY results good.")
	return results #True

def testVERIFY(res, nKu, host, port, num=CONCURRENT):
	logger.info("testVERIFY started...")
	dlist = []
	hashes = []
	for i in range(num):
		#if i == 4:
		#	port = 21
		fd = os.open(files[i], os.O_RDONLY)
		fsize = os.fstat(fd)[stat.ST_SIZE]
		length = 20
		offset = random.randrange(fsize-length)
		os.lseek(fd, offset, 0)
		data = os.read(fd, length)
		os.close(fd)
		hashes.append(FludCrypto.hashstring(data))
		filekey = os.path.basename(files[i])
		deferred = node.client.sendVerify(filekey, offset, length, host, 
				port, nKu)
		#deferred.addCallback(itersuccess, "succeeded at testVERIFY %d" % i)
		deferred.addErrback(itererror, "failed at testVERIFY %d: %s" 
				% (i, filekey))
		dlist.append(deferred)
	d = ErrDeferredList(dlist)
	d.addCallback(stagesuccess, "testVERIFY")
	d.addErrback(stageerror, 'failed at testVERIFY')
	d.addCallback(checkVERIFY, nKu, host, port, hashes, num)
	return d
	
def checkRETRIEVE(res, nKu, host, port, num=CONCURRENT):
	logger.info("  checking RETRIEVE results...")
	for i in range(num):
		f1 = open(files[i])
		filekey = os.path.basename(files[i])
		f2 = open(node.config.clientdir+"/"+filekey)
		if (f1.read() != f2.read()):
			f1.close()
			f2.close()
			raise failure.DefaultException("upload/download files don't match")
		f2.close()
		f1.close()
	logger.info("  ...RETRIEVE results good.")
	return testVERIFY(res, nKu, host, port, num)

def testRETRIEVE(res, nKu, host, port, num=CONCURRENT):
	logger.info("testRETRIEVE started...")
	dlist = []
	for i in range(num):
		#if i == 4:
		#	port = 21
		filekey = os.path.basename(files[i])
		deferred = node.client.sendRetrieve(filekey, host, port, nKu)
		#deferred.addCallback(itersuccess, "succeeded at testRETRIEVE %d" % i)
		deferred.addErrback(itererror, "failed at testRETRIEVE %d: %s" 
				% (i, filekey))
		dlist.append(deferred)
	d = ErrDeferredList(dlist)
	d.addCallback(stagesuccess, "testRETRIEVE")
	d.addErrback(stageerror, 'failed at testRETRIEVE')
	d.addCallback(checkRETRIEVE, nKu, host, port, num)
	return d

def testSTORE(nKu, host, port, num=CONCURRENT):
	logger.info("testSTORE started...")
	dlist = []
	for i in range(num):
		#if i == 4:
		#	port = 21
		deferred = node.client.sendStore(files[i], None, host, port, nKu)
		#deferred.addCallback(itersuccess, "succeeded at testSTORE %d" % i)
		deferred.addErrback(itererror, "failed at testSTORE %d" % i)
		dlist.append(deferred)
	d = ErrDeferredList(dlist)
	d.addCallback(stagesuccess, "testSTORE")
	d.addErrback(stageerror, 'failed at testSTORE')
	d.addCallback(testRETRIEVE, nKu, host, port, num)
	#d.addCallback(testVERIFY, nKu, host, port, num)
	return d

def testID(host, port, num=CONCURRENT):
	logger.info("testID started...")
	dlist = []
	for i in range(num):
		#if i == 4:
		#	port = 21
		deferred = node.client.sendGetID(host, port)
		deferred.debug = True
		deferred.addErrback(itererror, "failed at testID %d" % i)
		dlist.append(deferred)
	d = ErrDeferredList(dlist, returnOne=True)
	d.addCallback(stagesuccess, "testID")
	d.addErrback(stageerror, 'testID')
	d.addCallback(testSTORE, host, port, num)
	return d
	
def runTests(host, port=None, listenport=None):
	num = CONCURRENT
	#num = 5
	global files, node
	files = createFakeData()
	node = FludNode(port=listenport)
	if port == None:
		port = node.config.port
	node.run()

	if num > len(files):
		num = len(files)
	
	d1 = testID(host, port, num)
	d1.addCallback(suitesuccess)
	d1.addErrback(suiteerror)
	d1.addBoth(cleanup)

	#nku = FludRSA.importPublicKey({'e': 65537L, 'n': 138646504113696863667807411690225283099791076530135000331764542300161152585426296356409290228001197773401729468267448145387041995053893737880473447042984919037843163552727823101445272608470814297563395471329917904393936481407769396601027233955938405001434483474847834031774504827822809611707032477570548179411L})
	#d2 = testSTORE(nku, node, host, port, files, num)
	#d2.addErrback(suiteerror, 'failed at %s' % d2.testname)

	node.join()
	#node.start()  # doesn't work, because reactor may not have started 
	               # listening by time requests start flying

def createFakeData(dir="/tmp", num=CONCURRENT):
	randsrc = open("/dev/urandom", 'rb')
	files = []
	for i in range(num):
		randdata = randsrc.read(256)
		filekey = fencode(int(FludCrypto.hashstring(randdata), 16))
		filename = dir+'/'+filekey
		f = open(filename, 'wb')
		f.write(randdata)
		f.close()
		files.append(filename)
	randsrc.close()
	return files

def deleteFakeData(files):
	for f in files:
		if os.path.exists(f):
			os.remove(f)
		else:
			logger.warn("s already deleted!" % f)

def cleanup(dummy=None):
	logger.info("cleaning up files and shutting down in 1 seconds...")
	time.sleep(1)
	deleteFakeData(files)
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
