"""
FludClient.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

flud client ops. 
"""

from twisted.web import client
from twisted.internet import error
import os, stat, httplib, sys, logging

from ClientPrimitives import *
from ClientDHTPrimitives import *
import FludCommUtil

logger = logging.getLogger('flud.client')

class FludClient(object):
	"""
	This class contains methods which create request objects
	"""
	def __init__(self, node):
		self.node = node
		self.currentStorOps = {}
	
	"""
	Data storage primitives
	"""
	def redoTO(self, f, node, host, port):
		print "in redoTO: %s" % f
		#print "in redoTO: %s" % dir(f.getTraceback())
		if f.getTraceback().find("error.TimeoutError"): 
			print "retrying........"
			return self.sendGetID(host, port)
		else:
			return f

	def sendGetID(self, host, port):
		#return SENDGETID(self.node, host, port).deferred
		d = SENDGETID(self.node, host, port).deferred
		#d.addErrback(self.redoTO, self.node, host, port)
		return d

	# XXX: we should cache nKu so that we don't do the GETID for all of these
	# ops every single time
	def sendStore(self, filename, metadata, host, port, nKu=None):
		# XXX: need to keep a map of 'filename' to deferreds, in case we are
		# asked to store the same chunk more than once concurrently (happens
		# for 0-byte files or from identical copies of the same file, for
		# example).  both SENDSTORE and AggregateStore will choke on this.
		# if we find a store req in said map, just return that deferred instead
		# of redoing the op. [note, could mess up node choice... should also do
		# this on whole-file level in FileOps]

		# XXX: need to remove from currentStorOps on success or failure
		key = "%s:%d:%s" % (host, port, filename)

		if self.currentStorOps.has_key(key):
			logger.debug("returning saved deferred for %s in sendStore" 
					% filename)
			return self.currentStorOps[key]

		def sendStoreWithnKu(nKu, host, port, filename, metadata):
			return SENDSTORE(nKu, self.node, host, port, filename, 
					metadata).deferred

		def removeKey(r, key):
			self.currentStorOps.pop(key)
			return r

		if not nKu:
			# XXX: doesn't do AggregateStore if file is small.  Can fix by
			#      moving this AggStore v. SENDSTORE choice into SENDSTORE 
			#      proper
			logger.warn("not doing AggregateStore on small file because"
					" of missing nKu")
			print "not doing AggregateStore on small file because" \
					" of missing nKu"
			d = self.sendGetID(host, port)
			d.addCallback(sendStoreWithnKu, host, port, filename, metadata)
			self.currentStorOps[key] = d
			return d

		fsize = os.stat(filename)[stat.ST_SIZE];
		if fsize < MINSTORSIZE:
			logger.debug("doing AggStore")
			if metadata:
				logger.debug("with metadata")
			d = AggregateStore(nKu, self.node, host, port, filename, 
					metadata).deferred
		else:
			logger.debug("SENDSTORE")
			d = SENDSTORE(nKu, self.node, host, port, filename, 
					metadata).deferred
		self.currentStorOps[key] = d
		d.addBoth(removeKey, key)
		return d
	
	# XXX: need a version that takes a metakey, too
	def sendRetrieve(self, filekey, host, port, nKu=None, metakey=True):
		def sendRetrieveWithNKu(nKu, host, port, filekey, metakey=True):
			return SENDRETRIEVE(nKu, self.node, host, port, filekey, 
					metakey).deferred

		if not nKu:
			d = self.sendGetID(host, port)
			d.addCallback(sendRetrieveWithNKu, host, port, filekey, metakey)
			return d
		else:
			return SENDRETRIEVE(nKu, self.node, host, port, filekey,
					metakey).deferred
	
	def sendVerify(self, filekey, offset, length, host, port, nKu=None, 
			meta=None):
		def sendVerifyWithNKu(nKu, host, port, filekey, offset, length, 
				meta=True):
			return SENDVERIFY(nKu, self.node, host, port, filekey, offset, 
					length, meta).deferred

		if not nKu:
			d = self.sendGetID(host, port)
			d.addCallback(sendVerifyWithNKu, host, port, filekey, offset, 
					length, meta)
			return d
		else:
			s = SENDVERIFY(nKu, self.node, host, port, filekey, offset, length,
					meta)
			return s.deferred
	
	def sendDelete(self, filekey, metakey, host, port, nKu=None):
		def sendDeleteWithNKu(nKu, host, port, filekey, metakey):
			return SENDDELETE(nKu, self.node, host, port, filekey,
					metakey).deferred

		if not nKu:
			d = self.sendGetID(host, port)
			d.addCallback(sendDeleteWithNKu, host, port, filekey, metakey)
			return d
		else:
			return SENDDELETE(nKu, self.node, host, port, filekey,
					metakey).deferred
	
	"""
	DHT single primitives (single call to single peer).  These should probably
	only be called for testing or bootstrapping (sendkFindNode can be used to
	'connect' to the flud network via a gateway, for instance).  Use the
	recursive primitives for doing DHT ops.
	"""
	def sendkFindNode(self, host, port, key):
		return SENDkFINDNODE(self.node, host, port, key).deferred

	def sendkStore(self, host, port, key, val):
		return SENDkSTORE(self.node, host, port, key, val).deferred

	def sendkFindValue(self, host, port, key):
		return SENDkFINDVALUE(self.node, host, port, key).deferred
	
	"""
	DHT recursive primitives (recursive calls to muliple peers)
	"""
	def kFindNode(self, key):
		return kFindNode(self.node, key).deferred
	
	def kStore(self, key, val):
		return kStore(self.node, key, val).deferred
	
	def kFindValue(self, key):
		return kFindValue(self.node, key).deferred
	
