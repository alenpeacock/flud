#!/usr/bin/python

import time, os, stat, random, sys, logging, socket, tempfile
from twisted.python import failure
from StringIO import StringIO
from zlib import crc32

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from flud.FludNode import FludNode
from flud.protocol.FludClient import FludClient
import flud.FludCrypto as FludCrypto
from flud.fencode import fencode, fdecode
from flud.protocol.FludCommUtil import *
from flud.FludDefer import ErrDeferredList

"""
Test code for primitive operations.  These ops include all of the descendents
of ROOT and REQUEST in FludProtocol.
"""

# metadatablock: (block#,n,k,blockdata)
metadatablock = fencode((1,20,40,'adfdsfdffffffddddddddddddddd'))
fake_mkey_offset = 111111

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

def checkDELETE(res, nKu, fname, fkey, mkey, node, host, port, totalDelete):
    """ checks to ensure the file was deleted """
    # totalDelete = True if this delete op should remove all meta (and data)
    if totalDelete:
        # try to retrieve with any metakey, should fail
        print "expecting failed retrieve, any metakey"
        return testRETRIEVE(res, nKu, fname, fkey, True, node, host, port,
                lambda args=(res, nKu): allGood(*args), False)
    else:
        # try to retrieve with any metakey, should succeed
        print "expecting successful retrieve, any metakey"
        return testRETRIEVE(res, nKu, fname, fkey, True, node, host, port,
                lambda args=(res, nKu, fname, fkey, mkey+fake_mkey_offset, 
                    node, host, port, True): testDELETE(*args))

def testDELETE(res, nKu, fname, fkey, mkey, node, host, port, totalDelete):
    """ Tests sendDelete, and invokes checkDELETE on success """
    print "starting testDELETE %s.%s" % (fname, mkey)
    #return checkDELETE(None, nKu, fname, fkey, mkey, node, host, port, False)
    deferred = node.client.sendDelete(fkey, mkey, host, port, nKu)
    deferred.addCallback(checkDELETE, nKu, fname, fkey, mkey, node, host, port,
            totalDelete)
    deferred.addErrback(testerror, "failed at testDELETE", node)
    return deferred

def checkVERIFY(res, nKu, fname, fkey, mkey, node, host, port, hash, newmeta):
    """ executes after testVERIFY """
    if long(hash, 16) != long(res, 16):
        raise failure.DefaultException("verify didn't match: %s != %s"
                % (hash, res))
    print "checkVERIFY (%s) %s success" % (newmeta, fname)
    if newmeta:
        return testDELETE(res, nKu, fname, fkey, mkey, node, host, port, False)
    else:
        return testVERIFY(nKu, fname, fkey, mkey, node, host, port, True)

def testVERIFY(nKu, fname, fkey, mkey, node, host, port, newmeta):
    """ Test sendVerify """
    # newmeta, if True, will generate new metadata to be stored during verify
    if newmeta: 
        thismkey = mkey+fake_mkey_offset
    else: 
        thismkey = mkey
    print "starting testVERIFY (%s) %s.%s" % (newmeta, fname, thismkey)
    
    fd = os.open(fname, os.O_RDONLY)
    fsize = os.fstat(fd)[stat.ST_SIZE]
    length = 20
    offset = random.randrange(fsize-length)
    os.lseek(fd, offset, 0)
    data = os.read(fd, length)
    os.close(fd)
    hash = FludCrypto.hashstring(data)
    deferred = node.client.sendVerify(fkey, offset, length, host, port, nKu,
            (thismkey, StringIO(metadatablock)))
    deferred.addCallback(checkVERIFY, nKu, fname, fkey, mkey, node, host, 
            port, hash, newmeta)
    deferred.addErrback(testerror, "failed at testVERIFY (%s)" % newmeta, node)
    return deferred

def failedRETRIEVE(res, nextCallable):
    return nextCallable();

def checkRETRIEVE(res, nKu, fname, fkey, mkey, node, host, port, nextCallable):
    """ Compares the file that was stored with the one that was retrieved """
    f1 = open(fname)
    filename = [f for f in res if f[-len(fkey):] == fkey][0]
    f2 = open(filename)
    if (f1.read() != f2.read()):
        f1.close()
        f2.close()
        raise failure.DefaultException(
                "upload/download (%s, %s) files don't match" % (fname, 
                    os.path.join(node.config.clientdir, fkey)))
    #print "%s (%d) and %s (%d) match" % (fname, os.stat(fname)[stat.ST_SIZE],
    #   filename, os.stat(filename)[stat.ST_SIZE])
    f1.close()
    f2.close()
    if mkey != True:
        expectedmeta = "%s.%s.meta" % (fkey, mkey)
        metanames = [f for f in res if f[-len(expectedmeta):] == expectedmeta]
        if not metanames:
            raise failure.DefaultException("expected metadata was missing")
        f3 = open(metanames[0])
        md = f3.read()
        if md != metadatablock:
            raise failure.DefaultException("upload/download metadata doesn't"
                    " match (%s != %s)" % (md, metadatablock))
    return nextCallable()

def testRETRIEVE(res, nKu, fname, fkey, mkey, node, host, port, nextCallable,
        expectSuccess=True):
    """ Tests sendRetrieve, and invokes checkRETRIEVE on success """
    print "starting testRETRIEVE %s.%s" % (fname, mkey)
    deferred = node.client.sendRetrieve(fkey, host, port, nKu, mkey)
    deferred.addCallback(checkRETRIEVE, nKu, fname, fkey, mkey, node, host, 
            port, nextCallable)
    if expectSuccess:
        deferred.addErrback(testerror, "failed at testRETRIEVE", node)
    else:
        deferred.addErrback(failedRETRIEVE, nextCallable)
    return deferred

def testSTORE2(nKu, fname, fkey, node, host, port):
    mkey = crc32(fname)
    mkey2 = mkey+(2*fake_mkey_offset)
    print "starting testSTORE %s.%s" % (fname, mkey2)
    deferred = node.client.sendStore(fname, (mkey2, StringIO(metadatablock)), 
            host, port, nKu)
    deferred.addCallback(testRETRIEVE, nKu, fname, fkey, mkey2, node, host,
            port, lambda args=(nKu, fname, fkey, mkey, node, host, port, 
                False): testVERIFY(*args))
    deferred.addErrback(testerror, "failed at testSTORE", node)
    return deferred

def testSTORE(nKu, fname, fkey, node, host, port):
    """ Tests sendStore, and invokes testRETRIEVE on success """
    mkey = crc32(fname)
    print "starting testSTORE %s.%s" % (fname, mkey)
    deferred = node.client.sendStore(fname, (mkey, StringIO(metadatablock)), 
            host, port, nKu)
    deferred.addCallback(testRETRIEVE, nKu, fname, fkey, mkey, node, host, port,
            lambda args=(nKu, fname, fkey, node, host, port): testSTORE2(*args))
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
    for fname, fkey in aggFiles:
        mkey = crc32(fname) 
        print "testAggSTORE %s (%s)" % (fname, mkey)
        deferred = node.client.sendStore(fname, (mkey, StringIO(metadatablock)),
                host, port, nKu)
        deferred.addCallback(testRETRIEVE, nKu, fname, fkey, mkey, node, host, 
                port, lambda args=(nKu, fname, fkey, mkey, node, host, 
                    port, False): testVERIFY(*args))
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

def main():
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

if __name__ == '__main__':
    main()
