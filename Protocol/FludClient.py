"""
FludClient.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

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
	def sendStore(self, filename, host, port, nKu=None):
		def sendStoreWithnKu(nKu, host, port, filename):
			return SENDSTORE(nKu, self.node, host, port, filename).deferred

		if not nKu:
			# XXX: doesn't do AggregateStore if filename is small.  Can fix by
			#      moving this AggStore v. SENDSTORE choice into SENDSTORE 
			#      proper
			d = self.sendGetID(host, port)
			d.addCallback(sendStoreWithnKu, host, port, filename)
			return d
		fsize = os.stat(filename)[stat.ST_SIZE];
		if fsize < MINSTORSIZE:
			return AggregateStore(nKu, self.node, host, port, filename).deferred
		d = SENDSTORE(nKu, self.node, host, port, filename).deferred
		return d
	
	def sendRetrieve(self, filekey, host, port, nKu=None):
		def sendRetrieveWithNKu(nKu, host, port, filekey):
			return SENDRETRIEVE(nKu, self.node, host, port, filekey).deferred

		if not nKu:
			d = self.sendGetID(host, port)
			d.addCallback(sendRetrieveWithNKu, host, port, filekey)
			return d
		else:
			return SENDRETRIEVE(nKu, self.node, host, port, filekey).deferred
	
	def sendVerify(self, filekey, offset, length, host, port, nKu=None):
		def sendVerifyWithNKu(nKu, host, port, filekey, offset, length):
			return SENDVERIFY(nKu, self.node, host, port, filekey, offset, 
					length).deferred

		if not nKu:
			d = self.sendGetID(host, port)
			d.addCallback(sendVerifyWithNKu, host, port, filekey, offset, 
					length)
			return d
		else:
			s = SENDVERIFY(nKu, self.node, host, port, filekey, offset, length)
			return s.deferred
	
	def sendDelete(self, filekey, host, port, nKu=None):
		def sendDeleteWithNKu(nKu, host, port, filekey):
			return SENDDELETE(nKu, self.node, host, port, filekey).deferred

		if not nKu:
			d = self.sendGetID(host, port)
			d.addCallback(sendDeleteWithNKu, host, port, filekey)
			return d
		else:
			return SENDDELETE(nKu, self.node, host, port, filekey).deferred
	
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
	
