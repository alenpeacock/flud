#!/usr/bin/python

"""
FludFileOpTest.py,  (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

System tests for FludFileOperations
"""

import sys, os, time, logging, tempfile, shutil
from twisted.internet import reactor

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
	os.path.abspath(__file__)))))
from flud.FludConfig import FludConfig
from flud.FludNode import FludNode
from flud.fencode import fencode, fdecode
from flud.FludCrypto import generateRandom
from flud.FludFileOperations import *
import flud.FludDefer as FludDefer
from flud.protocol.LocalClient import listMeta

logger = logging.getLogger('flud')

def testError(failure, message, node):
	print "testError message: %s" % message
	print "testError: %s" % str(failure)
	print "At least 1 test FAILED"
	return failure

def verifySuccess(r, desc):
	print "%s succeeded" % desc

def checkRetrieveFile(res, node, fname):
	print "retrieve of %s succeeded" % fname
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
			print "testing retrieve (%s) %s" % (desc, fname)
			d = testRetrieveFile(node, fname)
			d.addCallback(loop, node, filenamelist, desc)
			d.addErrback(testError)
			return d
		else:
			print "retrieve sequential (%s) done" % desc

	print "test retrieveSequential %s" % desc
	return loop(None, node, filenamelist, desc)

def storeSuccess(r, desc):
	print "%s succeeded" % desc

def storeConcurrent(r, node, files, desc):
	#print "r was %s" % r
	print "test storeConcurrent %s" % desc
	dlist = []
	for file in files:
		d = testStoreFile(node, file)
		dlist.append(d)
	dl = FludDefer.ErrDeferredList(dlist)
	dl.addCallback(storeSuccess, desc)
	dl.addErrback(testError)
	return dl

def checkStoreFile(res, node, fname):
	master = listMeta(node.config)
	if fname not in master:
		return defer.fail(failure.DefaultException("file not stored"))
	else:
		print "store of %s appeared successful" % fname
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
			print "deleting %s" % f
			os.remove(f)
		except:
			print "couldn't remove %s" % f
	reactor.callLater(1, node.stop)

def generateTestFile(minSize):
	fname = tempfile.mktemp()
	f = open(fname, 'w')
	data = generateRandom(minSize/50)
	for i in range(0, 51+random.randrange(50)):
		f.write(data)
	f.close()
	filename = os.path.join("/tmp",fname)
	os.rename(fname,filename)
	return filename

def runTests(host, port, listenport=None):
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

	d = doTests(node, [f1, f2], [f4, f5], [f2, f3], [f5, f6])
	d.addBoth(cleanup, node, [f1, f2, f3, f4, f5, f6])
	node.join()

if __name__ == '__main__':
	localhost = socket.getfqdn()
	if len(sys.argv) == 3: 
		runTests(sys.argv[1], eval(sys.argv[2])) # talk to [1] on port [2]
	elif len(sys.argv) == 4: 
		# talk to [1] on port [2], listen on port [3]
		runTests(sys.argv[1], eval(sys.argv[2]), eval(sys.argv[3]))
	else:
		print "must run this test against a flud network (no single node op)"
		print "usage: %s [<othernodehost othernodeport> |"\
				" <othernodehost othernodeport listenport>]" % sys.argv[0]
