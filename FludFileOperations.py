"""
FludFileOperations.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 2.

Implements file storage and retrieval operations using flud primitives.
"""

import os, stat, sys, logging, binascii, random, time
import FludCrypto
from twisted.internet import defer
from FludCrypto import FludRSA
from FludFileCoder import Coder, Decoder
from Protocol.FludCommUtil import *
from Crypto.Cipher import AES
from fencode import fencode, fdecode

logger = logging.getLogger('flud.fileops')

# erasure coding constants
code_k = 20
code_m = 20
code_l = 5
# temp filenaming defaults
appendEncrypt = ".crypt"
appendNodeMeta = ".nmeta"
dirReplace = "-"

# XXX: could remove trailing '=' from all stored sha256s (dht keys, storage
#      keys, etc) and add them back implicitly


def pathsplit(fname):
	par, chld = os.path.split(fname)
	if chld == "":
		res = []
		res.append(par)
		return res
	else:
		res = pathsplit(par)
		res.append(os.path.join(par,chld))
		return res

def filemetadata(fname):
	fstat = os.stat(fname)
	return {'path' : fname, 'mode' : fstat[stat.ST_MODE], 
		'uid' : fstat[stat.ST_UID], 'gid' : fstat[stat.ST_GID], 
		'atim' : fstat[stat.ST_ATIME], 'mtim' : fstat[stat.ST_MTIME], 
		'ctim' : fstat[stat.ST_CTIME]} 

class StoreFile:
	"""
	Implements the meta operations of storing, retrieving, and verifying files.
	In addition to using the data primitives laid out in the Protocol/
	directory, manages the creation of file metadata for local and remote
	storage.

	Stores a file to flud by:
	
	1. Create storage and encryption keys for file: Hashes the file once
	to create an encryption key, eK=H(file), and then again to create the
	storage key for the file metadata sK=H(eK)=H(H(file)). 

	2. Create node-specific file metadata: Encrypts the storage key
	asymetrically with public key as eeK=e_Ku(eK), and creates local copy
	of file metadata with eeK and other file metadata (ownership, name,
	timestamps).  Encrypts this metadata with Ku. (flud file metadata
	consists of eeK and Ku(file metadata)).
	
	3. Create data-specific file metadata: Symmetrically encrypt the file
	with e_file=eK(file). Code e_file into k+m blocks.  Perform
	H(block) on each k+m block.

	4. Query DHT for sK.  If it exists, grab the metadata record (call it
	'storedMetadata') for comparison to one we are generated.  Compare
	data-specific metadata to storedMetadata (if it exists).  If it doesn't
	already exist, this step can be ignored.  If it exists and the data
	doesn't match, either the hash function is broken or a malicious node
	has poisoned the DHT -- return failure (client can attempt restore
	under a new key, or challenge the existing stored metadata).

	5. Store m+n blocks.  If stored metadata exists, can do VERIFYs
	instead, and only store when VERIFY fails.  For each failed VERIFY,
	must update the data-specific part of the metadata record.  Since we
	don't want to be susceptible to replacement attack, the update is
	treated as an 'append' to the specific block metadata by the store
	target.  (The store target can monitor its data-specific metadata
	records and for any that grow beyond a certain size, can shrink all
	block records to a size of 1 by performing RETRIEVE ops on the
	block, verfiying hash, and removing any failures.  If this fails for
	all block entries, can prune all but the /first and last/ entries --
	keep these to prevent damage by malicious nodes.  This strategy is
	beneficial to the node that performs it, because it prevents storage of
	arbitrary data in the DHT layer, which is in turn good for the system
	as a whole)

	6. Store file metadata (both node-specific and data-specific) to the
	DHT.  Keep a local copy as well.

	7. Update the master file record index for this node, and store it to
	the DHT layer.
	"""

	# XXX: should follow this currentOps model for the other FludFileOps
	currentOps = {}

	def __init__(self, node, filename):
		self.node = node
		self.filename = filename
		self.config = node.config
		self.Ku = node.config.Ku
		self.routing = self.config.routing
		self.metadir = self.config.metadir
		self.metamaster = os.path.join(self.metadir,self.config.metamaster)
		self.parentcodedir = self.config.clientdir # XXX: clientdir?

		self.deferred = self._storeFile()
		
	def _storeFile(self):
		if not os.path.isfile(self.filename):
			return defer.fail(ValueError("%s is not a file" % self.filename))

		# 1: create encryption key (eK) and storage key (sK).  Query DHT using
		#    sK
		self.eK = FludCrypto.hashfile(self.filename)
		self.sK = long(FludCrypto.hashstring(self.eK), 16)
		self.eeK = self.Ku.encrypt(binascii.unhexlify(self.eK))
		self.eKey = AES.new(binascii.unhexlify(self.eK))
		#logger.debug("file %s eK:%s, storage key:%d" 
		#		% (self.filename, self.eK, self.sK))

		# 2: create file metadata locally.
		sbody = filemetadata(self.filename)
		sbody = fencode(sbody)
		self.eNodeFileMetadata = ""
		for i in range(0, len(sbody), 128):
			self.eNodeFileMetadata += self.Ku.encrypt(sbody[i:i+128])[0]
		self.nodeFileMetadata = {'eeK' : fencode(self.eeK[0]), 
				'meta' : fencode(self.eNodeFileMetadata)}
		# XXX: "/" is OS specific... tsk tsk
		self.flatname = self.filename.replace("/", dirReplace)
		self.mfilename = os.path.join(self.metadir,self.flatname+appendNodeMeta)
		f = open(self.mfilename, "w")
		f.write(fencode(self.nodeFileMetadata))
		f.close();

		# if already storing identical file by CAS, piggyback on it
		if self.currentOps.has_key(self.eK):
			logger.debug("reusing callback on %s" % self.eK)
			(d, counter) = self.currentOps[self.eK]
			self.currentOps[self.eK] = (d, counter+1)
			# setting sfile, encodedir, and efilename to empty vals is kinda
			# hokey -- could split _storeMetadata into two funcs instead (the
			# cleanup part and the store part; see _storeMetadata)
			self.sfiles = []
			self.encodedir = None
			self.efilename = None
			d.addCallback(self._piggybackStoreMetadata)
			return d

		# 3: encrypt and encode the file locally.
		self.efilename = os.path.join(self.metadir,self.flatname+appendEncrypt)
		e = open(self.efilename, "w")
		fd = os.open(self.filename, os.O_RDONLY)
		fstat = os.fstat(fd)
		fsize = fstat[stat.ST_SIZE]
		# create a pad at front of file to make it an even multiple of 16
		fpad = int(16 - fsize%16);
		#logger.debug("fsize=%d, padding with %d bytes" % (fsize, fpad))
		paddata = chr(fpad)+(fpad-1)*'\x00'
		buf = paddata + os.read(fd,16-len(paddata))
		e.write(self.eKey.encrypt(buf));
		# now write the rest of the file
		while 1:
			# XXX: can we do this in larger than 16-byte chunks?
			buf = os.read(fd,16)
			if buf == "":
				break
			e.write(self.eKey.encrypt(buf));
		e.close()
		os.close(fd)
		# code the file
		c = Coder(code_k, code_m, code_l)
		self.encodedir = os.path.join(self.parentcodedir, self.flatname)
		try:
			os.mkdir(self.encodedir)
		except:
			return defer.fail(failure.DefaultException(
				"%s already requested" % self.filename))
		self.sfiles = c.codeData(self.efilename, 
				os.path.join(self.encodedir, 'c'))
		#logger.debug("coded to: %s" % str(self.sfiles))
		# take hashes and rename coded blocks
		self.segHashesLocal = []
		for i in range(len(self.sfiles)):
			sfile = self.sfiles[i]
			h = long(FludCrypto.hashfile(sfile),16)
			logger.debug(" file block %s hashes to %s" % (i, fencode(h)))
			destfile = os.path.join(self.encodedir,fencode(h))
			if os.path.exists(destfile):
				logger.warn(" %s exists (%s)" % (destfile, fencode(h)))
			self.segHashesLocal.append(h)
			#logger.debug("moved %s to %s" % (sfile, destfile))
			os.rename(sfile, destfile)
			self.sfiles[i] = destfile

		# 4a: query DHT for metadata.
		d = self.node.client.kFindValue(self.sK)
		d.addCallback(self._checkForExistingFileMetadata)
		d.addErrback(self._storeFileErr, "DHT query for metadata failed")
		self.currentOps[self.eK] = (d, 1)
		return d

	# 4b: compare hashlists (locally encrypted vs. DHT -- if available).
	#     for lhash, dhash in zip(segHashesLocal, segHashesDHT):
	def _checkForExistingFileMetadata(self, storedMetadata):
		if storedMetadata == None or isinstance(storedMetadata, dict):
			logger.info("metadata doesn't yet exist, storing all data")
			d = self._storeBlocks(storedMetadata)
			#d = self._storeBlocksSKIP(storedMetadata)
			return d
		else:
			storedMetadata = fdecode(storedMetadata)
			logger.info("metadata exists, verifying all data")
			if not self._compareMetadata(storedMetadata['b'], self.sfiles):
				raise ValueError("stored and local metadata do not match")
			else:
				logger.info("stored and local metadata match.")
			# XXX: need to check for diversity.  It could be that data stored
			# previously to a smaller network (<k+m nodes) and that we should
			# try to increase diversity and re-store the data.
			# XXX: also need to make sure we still trust all the nodes in the
			# metadata list.  If not, we should move those blocks elsewhere.
			d = self._verifyAndStoreBlocks(storedMetadata)
			return d

	def _storeBlocksSKIP(self, storedMetadata):
		# for testing -- skip stores so we can get to storeMeta
		dlist = []
		self.blockMetadata = {}
		for i in range(len(self.segHashesLocal)):
			hash = self.segHashesLocal[i]
			sfile = self.sfiles[i]
			node = random.choice(self.routing.knownExternalNodes())
			host = node[0]
			port = node[1]
			nID = node[2]
			nKu = FludRSA.importPublicKey(node[3])
			#self.blockMetadata[hash] = (fencode(nKu.exportPublicKey()['n']), 
			#		host, port)
			self.blockMetadata[hash] = (long(nKu.id(), 16), host, port)
			#self.blockMetadata[hash] = long(nKu.id(), 16)
		return self._storeMetadata(None)

	# 5a -- store all blocks
	def _storeBlocks(self, storedMetadata):
		dlist = []
		self.blockMetadata = {}
		for i in range(len(self.segHashesLocal)):
			hash = self.segHashesLocal[i]
			sfile = self.sfiles[i]
			deferred = self._storeBlock(hash, sfile)
			dlist.append(deferred)
		dl = defer.DeferredList(dlist)
		dl.addCallback(self._storeMetadata)
		return dl

	def _storeBlock(self, hash, sfile, retry=2):
		nodeChoices = self.routing.knownExternalNodes()
		if not nodeChoices:
			return defer.fail(failure.DefaultException(
				"cannot store blocks to 0 nodes"))
		node = random.choice(nodeChoices)
		host = node[0]
		port = node[1]
		nID = node[2]
		nKu = FludRSA.importPublicKey(node[3])
		logger.info("STOREing under %s on %s:%d" % (fencode(hash), host, port))
		#self.blockMetadata[hash] = (long(nKu.id(),16), host, port)
		self.blockMetadata[hash] = long(nKu.id(), 16)
		deferred = self.node.client.sendStore(sfile, host, port, nKu) 
		deferred.addCallback(self._fileStored, hash)
		deferred.addErrback(self._retryStoreBlock, hash, sfile,
				"%s (%s:%d)" % (fencode(nID), host, port), retry)
		return deferred

	def _retryStoreBlock(self, error, hash, sfile, badtarget, retry=None): 
		retry = retry - 1
		if retry > 0:
			logger.warn("STORE to %s failed, trying again" % badtarget)
			d = self._storeBlock(hash, sfile, retry)
			d.addCallback(self._fileStored, hash)
			# This will fail the entire operation.  This is correct
			# behavior because we've tried on at least N nodes and couldn't
			# get the block to store -- the caller will have to try the entire
			# op again.  If this proves to be a problem, up the default retry
			# value in _storeBlock().
			d.addErrback(self._storeFileErr, "couldn't store block %s" 
					% fencode(hash))
			return d
		else:
			logger.warn("STORE to %s failed, giving up" % badtarget)
			d = defer.Deferred()
			d.addErrback(self._storeFileErr, "couldn't store block %s"
					% fencode(hash))
			d.errback()
			return d

	def _fileStored(self, result, hash):
		return fencode(hash)

	def _compareMetadata(self, storedFiles, fileNames):
		# compares the block names returned from DHT to those in fileNames.
		# @param storedFiles: dict of longs (hashes) to their locations, 
		#                     usually obtained from storedMetadata['b']
		# @param fileNames: local filenames.  Only the os.path.basename part 
		#                     will be used for comparison
		# @return true if they match up perfectly, false otherwise
		logger.debug(' # remote block names: %d' % len(storedFiles))
		logger.debug(' # local blocks: %d' % len(fileNames))
		result = True
		for i in storedFiles:
			fname = os.path.join(self.encodedir,fencode(i))
			if not fname in fileNames:
				logger.warn("%s not in sfiles" % fencode(i))
				result = False
		for i in fileNames:
			hname = os.path.basename(i)
			if not storedFiles.has_key(fdecode(hname)):
				logger.warn("%s not in storedMetadata" % hname)
				result = False
		if result == False:
			for i in storedFiles:
				logger.debug("storedBlock = %s" % fencode(i))
			for i in fileNames:
				logger.debug("localBlock  = %s" % os.path.basename(i))
		return result

	# 5b -- findnode on all stored blocks. 
	def _verifyAndStoreBlocks(self, storedMetadata):
		self.blockMetadata = storedMetadata['b']
		dlist = []
		for sfile in self.sfiles:
			seg = os.path.basename(sfile)
			segl = fdecode(seg)
			nid = self.blockMetadata[segl]
			if isinstance(nid, list):
				logger.info("multiple location choices, choosing one randomly.")
				nid = random.choice(nid)
				# XXX: for now, this just picks one of the alternatives at
				#      random.  If the chosen one fails, should try each of the
				#      others until it works
			logger.info("looking up %s..." % ('%x' % nid)[:8])
			deferred = self.node.client.kFindNode(nid)
			deferred.addCallback(self._verifyBlock, sfile, seg, segl, nid)
			deferred.addErrback(self._storeFileErr, 
					"couldn't find node %s... for VERIFY" % ('%x' % nid)[:8], 
					False)
			dlist.append(deferred)
		dl = defer.DeferredList(dlist)
		dl.addCallback(self._storeMetadata)
		return dl

	# 5c -- verify all blocks, store any that fail verify.
	def _verifyBlock(self, kdata, sfile, seg, segl, nid):
		# XXX: looks like we occasionally get in here on timed out connections.
		#      Should go to _storeFileErr instead, eh?
		if isinstance(kdata, str):
			logger.err("str kdata=%s" % kdata)
		#if len(kdata['k']) > 1:
		#	#logger.debug("type kdata: %s" % type(kdata))
		#	#logger.debug("kdata=%s" % kdata)
		#	#logger.debug("len(kdata['k'])=%d" % len(kdata['k']))
		#	raise ValueError("couldn't find node %s" % ('%x' % nid))
		#	#raise ValueError("this shouldn't really be a ValueError..."
		#	#		" should be a GotMoreKnodesThanIBargainedForError"
		#	#		" (possibly caused when kFindNode fails (timeout) and"
		#	#		" we just get our own list of known nodes?): k=%s"
		#	#		% kdata['k'])
		node = kdata['k'][0]
		host = node[0]
		port = node[1]
		id = node[2]
		if id != nid:
			logger.debug("couldn't find node %s" % ('%x' %nid))
			raise ValueError("couldn't find node %s" % ('%x' % nid))
		nKu = FludRSA.importPublicKey(node[3])

		logger.info("verifying %s on %s:%d" % (seg, host, port))
		fd = os.open(sfile, os.O_RDONLY)
		fsize = os.fstat(fd)[stat.ST_SIZE]
		if fsize > 20: # XXX: 20?
			length = 20  # XXX: 20?
			offset = random.randrange(fsize-length)
		else:
			length = fsize
			offset = 0
		os.lseek(fd, offset, 0)
		data = os.read(fd, length)
		os.close(fd)
		verhash = long(FludCrypto.hashstring(data), 16)
		
		deferred = self.node.client.sendVerify(seg, offset, length, 
				host, port, nKu) 
		deferred.addCallback(self._checkVerify, nKu, host, port, segl, 
				sfile, verhash)
		deferred.addErrback(self._checkVerifyErr, segl, sfile, verhash)
		return deferred

	def _checkVerify(self, result, nKu, host, port, seg, sfile, hash):
		if hash != long(result, 16):
			logger.info("VERIFY hash didn't match for %s, performing STORE"
					% fencode(seg))
			d = self._storeBlock(seg, sfile)
			return d
		else:
			#logger.debug("block passed verify (%s == %s)" 
			#		% (hash, long(result,16)))
			return fencode(seg)

	def _checkVerifyErr(self, failure, seg, sfile, hash):
		logger.debug("Couldn't VERIFY: %s" % failure.getErrorMessage())
		logger.info("Couldn't VERIFY %s, performing STORE" % fencode(seg))
		d = self._storeBlock(seg, sfile)
		return d

	def _piggybackStoreMetadata(self, piggybackMeta):
		logger.debug("need to parse this %s: %s" 
				% (type(piggybackMeta), piggybackMeta))
		self.blockMetadata = piggybackMeta[1]['b']
		logger.debug("which is %s, i think", self.blockMetadata)
		return self._storeMetadata([])

	# 6 - store the metadata.
	def _storeMetadata(self, dlistresults):
		# cleanup part of storeMetadata:
		logger.debug("dlist=%s" % str(dlistresults))
		# XXX: for any "False" in dlistresults, need to invoke _storeBlocks
		#      again on corresponding entries in sfiles.
		for i in dlistresults:
			if i[1] == None:
				logger.info("failed store/verify")
				return False

		# clean up locally coded files and encrypted file
		for sfile in self.sfiles:
			os.remove(sfile)
			#logger.info("removed %s" % sfile)
		if self.encodedir: os.rmdir(self.encodedir)
		if self.efilename: os.remove(self.efilename)

		# storeMetadata part of storeMetadata
		meta = {self.config.nodeID: self.nodeFileMetadata, 
				'b' :self.blockMetadata}
		# XXX: should sign metadata to prevent forged entries.
		logger.debug("node metadata = %s" 
				% {self.config.nodeID: self.nodeFileMetadata})
		#for i in self.blockMetadata:
		#	logger.debug("  %s: %s" 
		#			% (fencode(i), fencode(self.blockMetadata[i])))
		logger.debug("storing metadata at %s" % fencode(self.sK))
		logger.info("len(segMetadata) = %d" % len(self.blockMetadata))
		logger.debug("len(meta) = %d" % len(str(meta)))
		logger.debug("len(nodemeta) = %d" % len(str(self.nodeFileMetadata)))
		logger.debug("len(segmmeta) = %d" % len(str(self.blockMetadata)))
		d = self.node.client.kStore(self.sK, meta) 
		d.addCallback(self._updateMaster, meta)
		d.addErrback(self._storeFileErr, "couldn't store file metadata to DHT")
		return d

	# 7 - update local master file record (store it to the network later).
	def _updateMaster(self, res, meta):
		key = fencode(self.sK)
		logger.info("updating local master metadata with %s" % key)
		# store the filekey locally
		# XXX: this isn't too efficient -- read whole file, add record, write
		#      whole file
		fmaster = open(self.metamaster, 'r')
		master = fmaster.read()
		fmaster.close()
		if master == "":
			master = {}
		else:
			master = fdecode(master)
		master[self.filename]=self.sK
		# XXX: need to store directory info for all parents of this file if
		#      not already present (perms, owner, timestamps, etc).
		paths = pathsplit(self.filename)
		for i in paths:
			if not i in master:
				master[i] = filemetadata(i)
		fmaster = open(self.metamaster, 'w')
		fmaster.write(fencode(master))
		fmaster.close()

		# cache the metadata locally (optional)
		fname = os.path.join(self.metadir,key)
		m = open(fname, 'wb')
		m.write(fencode(meta))
		m.close()

		# clean up local metadata file
		os.remove(self.mfilename)
		logger.info("removed %s" % self.mfilename)
		#return fencode(self.sK)
		(d, counter) = self.currentOps[self.eK]
		counter = counter - 1
		if counter == 0:
			logger.debug("counter 0 for currentOps %s" % self.eK)
			self.currentOps.pop(self.eK)
		else:
			logger.debug("setting counter = %d for %s" % (counter, self.eK))
			self.currentOps[self.eK] = (d, counter)
		return (key, meta)
		
	def _storeFileErr(self, failure, message, raiseException=True):
		(d, counter) = self.currentOps[self.eK]
		counter = counter - 1
		if counter == 0:
			logger.debug("err counter 0 for currentOps %s" % self.eK)
			self.currentOps.pop(self.eK)
		else:
			logger.debug("err setting counter = %d for %s" % (counter, self.eK))
			self.currentOps[self.eK] = (d, counter)
		logger.error("%s: %s" % (message, failure.getErrorMessage()))
		#logger.debug(failure.getTraceback())
		if raiseException:
			raise failure


class RetrieveFile:
	"""
	Uses the given storage key to retrieve a file.  The storage key is used
	to query the DHT layer for the file metadata record.  The file record
	contains the locations of the file blocks.  These are downloaded
	until the complete file can be regenerated and saved locally.
	"""

	def __init__(self, node, key):
		# 1: Query DHT for sK
		# 2: Retrieve entries for sK, decoding until efile can be regenerated
		# 3: Retrieve eK from sK by eK=Kp(eKe).  Use eK to decrypt file.  Strip
		#    off leading pad.
		# 4: Save file as filepath=Kp(efilepath).

		self.node = node
		try:
			self.sK = fdecode(key)
		except Exception, inst:
			self.deferred = defer.fail(inst)
			return
		self.config = node.config
		self.Ku = node.config.Ku
		self.Kr = node.config.Kr
		self.routing = self.config.routing.knownNodes()
		self.metadir = self.config.metadir
		self.metamaster = os.path.join(self.metadir,self.config.metamaster)
		self.parentcodedir = self.config.clientdir
		self.numDecoded = 0

		self.deferred = self._retrieveFile()
		
	def _retrieveFile(self):
		# 1: Query DHT for sK
		d = self.node.client.kFindValue(self.sK)
		d.addCallback(self._retrieveFileBlocks)
		d.addErrback(self._retrieveFileErr, "file retrieve failed")
		return d

	def _retrieveFileBlocks(self, meta):
		# 2: Retrieve entries for sK, decoding until efile can be regenerated
		if meta == None:
			raise LookupError("couldn't recover metadata for %s" % self.sK)
		self.meta = fdecode(meta)
		# XXX: need to check for diversity.  It could be that data stored
		# previously to a smaller network (<k+m nodes) and that we should
		# try to increase diversity and re-store the data.
		# XXX: also need to make sure we still trust all the nodes in the
		# metadata list.  If not, we should move those blocks elsewhere.
		if self.meta == None:
			raise LookupError("couldn't recover metadata for %s" % self.sK)
		logger.info("got metadata %s" % self.meta)
		for i in self.meta:
			if i == self.Ku.id():
				self.nmeta = self.meta[i]
				logger.info("got metadata for node %s:" % fencode(long(i,16)))
		self.decoded = False
		self.decoder = Decoder(os.path.join(self.parentcodedir,fencode(self.sK))
				+".rec1", code_k, code_m, code_l)
		#return self._getSomeBlocks()
		return self._getSomeBlocks(25) # XXX: magic. Should derive from k & m

	def _getSomeBlocks(self, reqs=40):  # XXX: magic 40. Should be k+m
		tries = 0
		if reqs > len(self.meta['b']):
			reqs = len(self.meta['b'])
		dlist = []
		for i in range(reqs):
			c = random.choice(self.meta['b'].keys())
			block = fencode(c)
			id = self.meta['b'][c]
			if isinstance(id, list):
				logger.info("multiple location choices, choosing one randomly.")
				id = random.choice(id)
				# XXX: for now, this just picks one of the alternatives at
				#      random.  If the chosen one fails, should try each of the
				#      others until it works
			#logger.info("retrieving %s from %s" % (block, fencode(id)))
			logger.info("retrieving %s from %s" % (block, id))			
			# look up nodes by id, then do a retrieve.
			deferred = self.node.client.kFindNode(id) 
			deferred.addCallback(self._retrieveBlock, block, id)
			deferred.addErrback(self._retrieveBlockErr, 
					"couldn't get block %s from node %s" % (block, fencode(id)))
			dlist.append(deferred)
			self.meta['b'].pop(c)
			tries = tries + 1
			if tries >= reqs:
				break;
		dl = defer.DeferredList(dlist)
		dl.addCallback(self._retrievedAll)
		return dl

	def _retrieveBlock(self, kdata, block, id):
		#print type(kdata)
		#print kdata
		#if len(kdata['k']) > 1:
		if kdata['k'][0][2] != id:
			print "%s != %s" (kdata['k'][0], id)
			raise ValueError("couldn't find node %s" % fencode(id))
			#raise ValueError("this shouldn't really be a ValueError..."
			#		" should be a GotMoreKnodesThanIBargainedForError: k=%s"
			#		% kdata['k'])
		#else:
		#	print kdata['k']
		node = kdata['k'][0]
		host = node[0]
		port = node[1]
		id = node[2]
		nKu = FludRSA.importPublicKey(node[3])
		if not self.decoded:
			d = self.node.client.sendRetrieve(block, host, port, nKu)
			d.addCallback(self._decodeBlock, block)
			d.addErrback(self._retrieveBlockErr, 
					"couldn't get block %s from %s" % (block, fencode(id)))
			return d

	def _retrieveBlockErr(self, failure, message):
		logger.info("%s: %s" % (message, failure.getErrorMessage()))
		# don't propogate the error -- one block doesn't cause the file
		# retrieve to fail.
		#return failure

	def _retrievedAll(self, success):
		logger.info("tried retreiving %d blocks %s" % (len(success), success))
		if not self.decoded and len(self.meta['b']) > 0:
			tries = 5  # XXX: magic number. Should derive from k & m 
			logger.info("requesting %d more blocks" % tries)
			return self._getSomeBlocks(tries) 
		if self.decoded:
			logger.info("file successfully decoded")
			return self._decryptFile() 
		else:
			logger.info("couldn't decode file after retreiving all %d"
					" available blocks" %self.numDecoded)
			#return False
			raise RuntimeError("couldn't decode file after retreiving all %d" 
					" available blocks" %self.numDecoded)

	def _decodeBlock(self, msg, block):
		logger.debug("decode block=%s, msg=%s" % (block, msg))
		#self.meta['b'].pop(block)
		self.numDecoded += 1
		if not self.decoded and self.decoder.decodeData(
				os.path.join(self.parentcodedir,block)):
			self.decoded = True
			logger.info("successfully decoded (retrieved %d blocks --"
					" all but %d blocks tried)" % (self.numDecoded, 
						len(self.meta['b'])))
	
	def _decryptFile(self):
		# 3: Retrieve eK from sK by eK=Kr(eeK).  Use eK to decrypt file.  Strip
		#    off leading pad.
		skey = fencode(self.sK)
		f1 = open(os.path.join(self.parentcodedir,skey+".rec1"), "r")
		f2 = open(os.path.join(self.parentcodedir,skey+".rec2"), "w")
		#logger.info("decoding nmeta eeK for %s" % dir(self))
		eeK = fdecode(self.nmeta['eeK'])
		# d_eK business is to ensure that eK is zero-padded to 32 bytes
		d_eK = self.Kr.decrypt(eeK)
		d_eK = '\x00'*(32%len(d_eK))+d_eK # XXX: magic 32, should be keyspace/8
		eK = binascii.hexlify(d_eK)
		eKey = AES.new(binascii.unhexlify(eK))
		while 1:
			buf = f1.read(16)
			if buf == "":
				break;
			f2.write(eKey.decrypt(buf))
		f1.close()
		f2.close()
		os.remove(os.path.join(self.parentcodedir,skey+".rec1"))
		f2 = open(os.path.join(self.parentcodedir,skey+".rec2"), "r")
		f3 = open(os.path.join(self.parentcodedir,skey+".rec3"), "w")
		padlen = f2.read(1)
		#print "%s" % repr(padlen)
		padlen = ord(padlen)
		padlen -= 1
		#print "throwing away %d pad bytes" % padlen
		pad = f2.read(padlen) # throw away pad.
		while 1:
			buf = f2.read(16)
			if buf == "":
				break;
			f3.write(buf)
		f2.close()
		f3.close()
		os.remove(os.path.join(self.parentcodedir,skey+".rec2"))

		# 4: Move file to its correct path, imbue it with properties from 
		#    metadata.
		# XXX: should we make sure we can read metadata before downloading all
		#      the file data?
		#print "decoding nmeta meta"
		efmeta = fdecode(self.nmeta['meta'])
		fmeta = ""
		for i in range(0, len(efmeta), 128):
			fmeta += self.Kr.decrypt(efmeta[i:i+128])
		fmeta = fdecode(fmeta)
		
		result = [fmeta['path']]
		if os.path.exists(fmeta['path']):
			# file is already there -- compare it.  If different, save as
			# path.recovered and keep a list of these (to let the user know
			# that they'll need to resolve later).  Or don't keep a list and
			# just 'do the right thing' (use the latest version by timestamp,
			# or always use the backup, or always use the local copy, or 
			# define some other behavior for doing the right thing).
			logger.info("hash rec=%s" % FludCrypto.hashfile(fmeta['path']))
			logger.info("hash org=%s" % eK)
			if FludCrypto.hashfile(fmeta['path']) != eK:
				# XXX: do something better than log it -- see above comment
				logger.info('different version of file %s already present' 
						% fmeta['path'])
				# XXX: should generate '.recovered' extension more carefully,
				#      so as not to overwrite coincidentally named files.
				fmeta['path'] = fmeta['path']+".recovered"
				result.insert(0,fmeta['path'])
				os.rename(os.path.join(self.parentcodedir,skey+".rec3"),
						fmeta['path'])
			else:
				logger.info('same version of file %s already present'
						% fmeta['path']) 
				# no need to copy:
				os.remove(os.path.join(self.parentcodedir,skey+".rec3")) 
		else:
			# recover parent directories of not present
			fmaster = open(self.metamaster, 'r')
			master = fmaster.read()
			fmaster.close()
			if master == "":
				master = {}
			else:
				master = fdecode(master)
			paths = pathsplit(fmeta['path'])
			for i in paths:
				if not os.path.exists(i) and i != fmeta['path']:
					os.mkdir(i) # best effort dir creation, even if missing
					              # directory metadata
					if i in master:
						dirmeta = master[i]
						os.chmod(i,dirmeta['mode'])	
						os.chown(i,dirmeta['uid'],dirmeta['gid']) # XXX: windows
						# XXX: atim, mtim, ctim
					# XXX: should try to make sure we can write to dir, change
					# perms if necessary.
			# recover file by renaming to its path 
			os.rename(os.path.join(self.parentcodedir,skey+".rec3"), 
					fmeta['path'])

		# XXX: chown not supported on Windows
		os.chown(fmeta['path'], fmeta['uid'], fmeta['gid'])
		os.utime(fmeta['path'], (fmeta['atim'], fmeta['mtim']))
		os.chmod(fmeta['path'], fmeta['mode'])
		return tuple(result)

	def _retrieveFileErr(self, failure, message, raiseException=True):
		logger.error("%s: %s" % (message, failure.getErrorMessage()))
		if raiseException:
			return failure

class RetrieveFilename:
	"""
	Retrieves a File given its local name.  Only works if the local master index
	contains an entry for this filename.
	"""

	def __init__(self, node, filename):
		self.node = node
		self.filename = filename
		self.metadir = self.node.config.metadir
		self.metamaster = os.path.join(self.metadir,self.node.config.metamaster)

		self.deferred = self._recoverFile()
		
	def _recoverFile(self):
		fmaster = open(self.metamaster, 'r')
		master = fmaster.read()
		fmaster.close()
		if master == "":
			master = {}
		else:
			master = fdecode(master)
		if master.has_key(self.filename):
			filekey = master[self.filename]
			if filekey != None and filekey != "":
				d = RetrieveFile(self.node, fencode(filekey)).deferred
				return d
			return defer.fail(LookupError("bad filekey %s for %s" 
					% (filekey, self.filename)))
		return defer.fail(LookupError("no record of %s" % self.filename))


class VerifyFile:
	# XXX: remove me?  I don't do anything that StoreFile can't do, plus if
	#      I fail you'd still need to call StoreFile right after...
	#      Or, do we keep me around and rip out all the verify stuff from
	#      StoreFile and put it in here?

	def verifyFile(self, filepath):
		"""
		Chooses some random blocks from filepath to verify against the store.
		The algorithm is as follows: sK = H(H(file at filepath)).  Look up sK
		in the local master index.  If the record isn't there, return this
		fact.  If the record is there, retrieve its metadata.  Verify k
		blocks as follows:
		
		With probibility n/(m+n), code the file locally (to verify coded
		blocks with a fair probabiliy, i.e., if m=40 and n=20, 33% of the
		time we will do the coding).  

		Choose k blocks from the resulting blocks and using the file
		metadata record, do a VERIFY operation using a random offset and random
		length (if we chose not to do the coding in the previous step, the k
		blocks must come entirely from the non-coded portion).  As we wait
		for the VERIFYs to return, hash these blocks locally.  As each VERIFY
		returns, compare it with our local hash just computed.  Return a list
		of hosts/nodeids for which the VERIFY failed.
		"""
		pass #remove me
		

class RetrieveMasterIndex:
	
	def __init__(self, node):
		self.node = node
		nodeID = long(self.node.config.nodeID, 16)
		# 1. CAS = kfindval(nodeID) (CAS for last FLUDHOME/meta/master)
		logger.info("looking for key %x" % nodeID)
		self.deferred = self.node.client.kFindValue(nodeID)
		self.deferred.addCallback(self._foundCAS)
		self.deferred.addErrback(self._retrieveMasterIndexErr, 
				"couldn't find master metadata")

	def _foundCAS(self, CAS):
		# 2. oldmaster = kfindval(CAS)
		if isinstance(CAS, dict):
			return defer.fail(ValueError("couldn't find CAS key"))
		CAS = fdecode(CAS)
		d = RetrieveFile(self.node, CAS).deferred
		d.addCallback(self._foundMaster)
		d.addErrback(self._retrieveMasterIndexErr, "couldn't find Master Index")
		return d

	def _foundMaster(self, result):
		if len(result) == 2: 
			# got two filenames back, must mean we should choose one: the
			# one from the distributed store
			os.rename(result[0], result[1])
			result = (result[1],)
		return result

	def _retrieveMasterIndexErr(self, err, msg):
		logger.warn(msg)
		return err

class UpdateMasterIndex:

	def __init__(self, node):
		self.node = node
		self.metamaster = os.path.join(self.node.config.metadir,
				self.node.config.metamaster)
		# 0.1. oldmaster = RetrieveMasterIndex()
		self.deferred = RetrieveMasterIndex(node).deferred
		self.deferred.addCallback(self._removeOldMasterIndex)
		self.deferred.addErrback(self._storeMasterIndex)

	def _removeOldMasterIndex(self, res):
		# 0.2. for i in oldmaster['b']: delete(i)
		print "removing old master not yet implemented"
		return self._storeMasterIndex(res)

	def _storeMasterIndex(self, res_or_err):
		# 1. store FLUDHOME/meta/master
		print "going to store %s" % self.metamaster
		d = StoreFile(self.node, self.metamaster).deferred
		d.addCallback(self._updateCAS)
		d.addErrback(self._updateMasterIndexErr, "couldn't store master index")
		return d

	def _updateCAS(self, stored):
		# 2. kstore(nodeID, CAS(FLUDHOME/meta/master))
		#print "stored = %s" % str(stored)
		key, meta = stored
		logger.info("storing %s at %x" % (key, 
			long(self.node.config.nodeID,16)))
		d = self.node.client.kStore(long(self.node.config.nodeID,16), 
				key)  # XXX: key should be fdecode()ed
		return d

	def _updateMasterIndexErr(self, err, msg):
		logger.warn(msg)
		return err


if __name__ == "__main__":
	from FludNode import FludNode

	def successTest(res, fname, whatfor, nextStage=None):
		logger.info("finished %s" % whatfor)

	def errTest(failure):
		logger.info("boom: %s" % failure.getErrorMessage())
		raise failure

	def fileKey(fname):
		EK = FludCrypto.hashfile(fname)
		return fencode(long(FludCrypto.hashstring(EK), 16))

	def clearMeta(fname):
		# delete any metadata that might exist for this file.
		try:
			SK = fileKey(fname)
			os.remove(os.path.join(n.config.kstoredir,SK))
			logger.info("test removed %s" % os.path.join(n.config.kstoredir,SK))
		except:
			pass
	
	def doStore(fname, msg=None, nextStage=successTest):
		if msg != None:
			logger.info("finished %s ------" % msg)
			logger.info("---------------------------------------------------\n")
		# do a store
		logger.info("nextStage is %s" % nextStage)
		d = StoreFile(n,fname).deferred
		d.addCallback(nextStage, fname, 'store op', doCorruptSegAndStore)
		d.addErrback(errTest)

	def doDelSegAndStore((key, meta), fname, msg=None, nextStage=successTest):
		# only works if stores are local
		if msg != None:
			logger.info("finished %s ------" % msg)
			logger.info("---------------------------------------------------\n")
		# delete a block and do a store
		c = random.choice(meta['b'].keys())
		logger.info("removing %s" % fencode(c))
		os.remove(os.path.join(n.config.storedir,fencode(c)))
		logger.info("test removed %s" % os.path.join(n.config.storedir,
			fencode(c)))
		d = StoreFile(n,fname).deferred
		d.addCallback(nextStage, fname, 'lost block op')
		d.addErrback(errTest)
		
	def doCorruptSegAndStore((key, meta), fname, msg=None, 
			nextStage=successTest):
		# only works if stores are local
		if msg != None:
			logger.info("finished %s ------" % msg)
			logger.info("---------------------------------------------------\n")
		# corrupt a block and do a store
		c = random.choice(meta['b'].keys())
		logger.info("corrupting %s" % fencode(c))
		f = open(os.path.join(n.config.storedir,fencode(c)), 'r')
		data = f.read()
		f.close()
		f = open(os.path.join(n.config.storedir,fencode(c)), 'w')
		f.write('blah'+data)
		f.close()
		d = StoreFile(n,fname).deferred
		d.addCallback(nextStage, fname, 'corrupted block op')
		d.addErrback(errTest)

	def doRetrieve(key, msg=None, nextStage=successTest):
		if msg != None:
			logger.info("finished %s ------" % msg)
			logger.info("---------------------------------------------------\n")
		d = RetrieveFile(n, key).deferred
		d.addCallback(nextStage, key, 'retrieve op')
		d.addErrback(errTest)

	def doRetrieveName(filename, msg=None, nextStage=successTest):
		if msg != None:
			logger.info("finished %s ------" % msg)
			logger.info("---------------------------------------------------\n")
		d = RetrieveFilename(n, filename).deferred
		d.addCallback(nextStage, filename, 'retrieve filename op')
		d.addErrback(errTest)
		
	def runTests(dummy):
			
		# test against self -- all stores and queries go to self.
		fname = "/tmp/nrpy.pdf"

		#clearMeta(fname)
		#doStore(fname, None, doDelSegAndStore)  # do all stages of testing
		doStore(fname)  # only do one op (for manual testing)

		#doRetrieve(fileKey(fname))

		#doRetrieveName(fname)


	n = FludNode()
	n.run()

	if len(sys.argv) == 3:
		deferred = n.client.sendkFindNode(sys.argv[1], int(sys.argv[2]), 1)
		deferred.addCallback(runTests)
		deferred.addErrback(errTest)
	else:
		runTests(None)


	n.join()
