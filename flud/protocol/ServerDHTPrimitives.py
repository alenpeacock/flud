"""
ServerDHTPrimitives.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

Primitive server DHT protocol
"""

import binascii, time, os, stat, httplib, gc, re, sys, logging, random, sets
from twisted.web.resource import Resource
from twisted.web import server, resource, http, client
from twisted.internet import reactor, defer
from twisted.python import failure

from flud.FludCrypto import FludRSA
from flud.fencode import fencode, fdecode

from ServerPrimitives import ROOT
from FludCommUtil import *

logger = logging.getLogger("flud.server.dht")

# XXX: move kRouting.insertNode code out of FludConfig.  Add a 'addNode' method
#      to FludProtocol module which calls config.addNode, calls
#      kRouting.insertNode and if it gets a return value, calls sendGetID with
#      the callback doing nothing (unless the header comes back in error) and
#      the errback calling kRouting.replaceNode.  Anywhere that we are
#      currently called config.addNode, call this new method instead. 
# FUTURE: check flud protocol version for backwards compatibility
# XXX: need to make sure we have appropriate timeouts for all comms.
# FUTURE: DOS attacks.  For now, assume that network hardware can filter these 
#      out (by throttling individual IPs) -- i.e., it isn't our problem.  If we
#      want to defend against this at some point, we need to keep track of who
#      is generating requests and then ignore them.
# XXX: find everywhere we are sending longs and consider sending hex (or our
#      own base-64) encoded instead
# XXX: might want to consider some self-healing for the kademlia layer, as 
#      outlined by this thread: 
#      http://zgp.org/pipermail/p2p-hackers/2003-August/001348.html (should also
#      consider Zooko's links in the parent to this post)


"""
The children of ROOT beginning with 'k' are kademlia protocol based.
"""
# XXX: need to do all the challenge/response jazz in the k classes

class kFINDNODE(ROOT):
	
	isLeaf = True
	def render_GET(self, request):
		"""
		Return the k closest nodes to the target ID from local k-routing table
		"""
		self.setHeaders(request)
		self.node.DHTtstamp = time.time()
		try:
			required = ('nodeID', 'Ku_e', 'Ku_n', 'port', 'key')
			params = requireParams(request, required)
		except Exception, inst:
			msg = inst.args[0] + " in request received by kFINDNODE" 
			logger.info(msg)
			request.setResponseCode(http.BAD_REQUEST, "Bad Request")
			return msg 
		else:
			logger.info("received kFINDNODE request from %s..."
					% params['nodeID'][:10])
			reqKu = {}
			reqKu['e'] = long(params['Ku_e'])
			reqKu['n'] = long(params['Ku_n'])
			reqKu = FludRSA.importPublicKey(reqKu)
			host = getCanonicalIP(request.getClientIP())
			#return "{'id': '%s', 'k': %s}"\
			#		% (self.config.nodeID,\
			#		self.config.routing.findNode(fdecode(params['key'])))
			kclosest = self.config.routing.findNode(fdecode(params['key']))
			notclose = list(set(self.config.routing.knownExternalNodes()) 
					- set(kclosest))
			if len(notclose) > 0 and len(kclosest) > 1:
				r = random.choice(notclose)
				#logger.info("**** got some notclose: %s:%d ****" % (r[0],r[1]))
				kclosest.append(r)
			#logger.info("returning kFINDNODE response: %s" % kclosest)
			updateNode(self.node.client, self.config, host, 
					int(params['port']), reqKu, params['nodeID'])
			return "{'id': '%s', 'k': %s}" % (self.config.nodeID, kclosest)
		
class kSTORE_true(ROOT):
	# unrestricted kSTORE.  Will store any key/value pair, as in generic
	# kademlia.  This should be unregistered in FludServer (can't allow
	# generic stores).
	isLeaf = True
	def render_PUT(self, request):
		self.setHeaders(request)
		try:
			required = ('nodeID', 'Ku_e', 'Ku_n', 'port', 'key', 'val')
			params = requireParams(request, required)
		except Exception, inst:
			msg = inst.args[0] + " in request received by kSTORE_true" 
			logger.info(msg)
			request.setResponseCode(http.BAD_REQUEST, "Bad Request")
			return msg 
		else:
			logger.info("received kSTORE_true request from %s..."
					% params['nodeID'][:10])
			reqKu = {}
			reqKu['e'] = long(params['Ku_e'])
			reqKu['n'] = long(params['Ku_n'])
			reqKu = FludRSA.importPublicKey(reqKu)
			host = getCanonicalIP(request.getClientIP())
			updateNode(self.node.client, self.config, host,
					int(params['port']), reqKu, params['nodeID'])
			fname = self.config.kstoredir+'/'+params['key']
			logger.info("storing dht data to %s" % fname)
			f = open(fname, "wb")
			f.write(params['val'])
			f.close()
			return "" 


class kSTORE(ROOT):
	# XXX: To prevent abuse of the DHT layer, we impose restrictions on its 
	#      format.  But format alone is not sufficient -- a malicious client
	#      could still format its data in a way that is allowed and gain
	#      arbitrary amounts of freeloading storage space in the DHT.  To
	#      prevent this, nodes storing data in the DHT layer must also validate
	#      it.  Validation simply requires that the blockIDs described in the
	#      kSTORE actually reside at a significant percentage of the hosts
	#      described in the kSTORE op.  In other words, validation requires a
	#      VERIFY op for each block described in the kSTORE op.  Validation can
	#      occur randomly sometime after a kSTORE operation, or at the time of
	#      the kSTORE op.  The former is better, because it not only allows
	#      purging bad kSTOREs, but prevents them from happening in the first
	#      place (without significant conspiring among all participants).
	#      Since the originator of this request also needs to do a VERIFY,
	#      perhaps we can piggyback these through some means.  And, since the
	#      kSTORE is replicated to k other nodes, each of which also should to
	#      a VERIFY, there are several ways to optimize this.  One is for the k
	#      nodes to elect a single verifier, and allow the client to learn the
	#      result of the VERIFY op.  Another is to allow each k node to do its
	#      own VERIFY, but stagger them in a way such that they can take the
	#      place of the originator's first k VERIFY ops.  This could be
	#      coordinated or (perhaps better) allow each k node to randomly pick a
	#      time at which it will VERIFY, distributed over a period for which it
	#      is likely to cover many of the first k VERIFY ops generated by
	#      the originator.  The random approach is nice because it is the same
	#      mechanism used by the k nodes to occasionally verify that the DHT
	#      data is valid and should not be purged.
	isLeaf = True
	def render_PUT(self, request):
		self.setHeaders(request)
		self.node.DHTtstamp = time.time()
		try:
			required = ('nodeID', 'Ku_e', 'Ku_n', 'port', 'key', 'val')
			params = requireParams(request, required)
		except Exception, inst:
			msg = inst.args[0] + " in request received by kSTORE" 
			logger.info(msg)
			request.setResponseCode(http.BAD_REQUEST, "Bad Request")
			return msg 
		else:
			logger.info("received kSTORE request from %s..." 
					% params['nodeID'][:10])
			reqKu = {}
			reqKu['e'] = long(params['Ku_e'])
			reqKu['n'] = long(params['Ku_n'])
			reqKu = FludRSA.importPublicKey(reqKu)
			host = getCanonicalIP(request.getClientIP())
			updateNode(self.node.client, self.config, host,
					int(params['port']), reqKu, params['nodeID'])
			fname = self.config.kstoredir+'/'+params['key']
			md = fdecode(params['val'])
			if not self.dataAllowed(params['key'], md, params['nodeID']):
				msg = "malformed store data"
				logger.info("bad data was: %s" % md)
				request.setResponseCode(http.BAD_REQUEST, msg)
				return msg
			# XXX: see if there isn't already a 'val' for 'key' present
			#      - if so, compare to val.  Metadata can differ.  Blocks
			#        shouldn't.  However, if blocks do differ, just add the
			#        new values in, up to N (3?) records per key.  Flag these
			#        (all N) as ones we want to verify (to storer and storee).
			#        Expunge any blocks that fail verify, and punish storer's 
			#        trust.
			logger.info("storing dht data to %s" % fname)
			if os.path.exists(fname) and isinstance(md, dict):
				f = open(fname, "rb")
				edata = f.read()
				f.close()
				md = self.mergeMetadata(md, fdecode(edata))
			f = open(fname, "wb")
			f.write(fencode(md))
			f.close()
			return ""  # XXX: return a VERIFY reverse request: segname, offset

	def dataAllowed(self, key, data, nodeID):
		# ensures that 'data' is in [one of] the right format[s] (helps prevent
		# DHT abuse)

		def validValue(val):
			if not isinstance(val, long) and not isinstance(val, int):
				return False  # not a valid key/nodeid
			if val > 2**256 or val < 0:  # XXX: magic 2**256, use fludkrouting
				return False  # not a valid key/nodeid
			return True

		def validMetadata(blockdata, nodeID):
			# returns true if the format of data conforms to the standard for
			# metadata 
			blocks = 0
			try:
				k = blockdata.pop('k')
				n = blockdata.pop('n')
				if not isinstance(k, int) or not isinstance(n, int):
					return False
				if k != 20 or n != 20:
					# XXX: magic numbers '20'
					# XXX: to support other than 20/20, need to constrain an
					# upper bound and store multiple records with different m/n
					# under the same key 
					return False
				m = k+n
			except:
				return False

			for (i, b) in blockdata:
				if i > m:
					return False
				if not validValue(b):
					#print "%s is invalid key" %i
					return False
				location = blockdata[(i,b)]
				if isinstance(location, list):
					if len(location) > 5:
						#print "too many (list) nodeIDs" % j
						return False
					for j in location:
						if not validValue(j):
							#print "%s is invalid (list) nodeID" % j
							return False
				elif not validValue(location):
					#print "%s is invalid nodeID" % location
					return False
				blocks += 1
			if blocks != m:
				return False   # not the right number of blocks
			blockdata['k'] = k
			blockdata['n'] = n
			return True

		def validMasterCAS(key, data, nodeID):
			# returns true if the data fits the characteristics of a master
			# metadata CAS key, i.e., if key==nodeID and the data is the right
			# length.
			nodeID = fencode(long(nodeID,16))
			if key != nodeID:
				return False  
			# XXX: need to do challange/response on nodeID (just as in the
			# regular primitives) here, or else imposters can store/replace
			# this very important data!!!
			# XXX: do some length stuff - should only be as long as a CAS key 
			return True

		return (validMetadata(data, nodeID) 
				or validMasterCAS(key, data, nodeID))
	
	def mergeMetadata(self, m1, m2):
		# merges the data from m1 into m2. After calling, both m1 and m2 
		# contain the merged data.
		"""
		>>> a1 = {'b': {1: (1, 'a', 8), 2: (2, 'b', 8), 5: (1, 'a', 8)}}
		>>> a2 = {'b': {1: (1, 'a', 8), 2: [(3, 'B', 80), (4, 'bb', 80)], 10: (10, 't', 80)}}
		>>> mergeit(a1, a2)
		{'b': {1: (1, 'a', 8), 2: [(3, 'B', 80), (4, 'bb', 80), (2, 'b', 8)], 10: (10, 't', 80), 5: (1, 'a', 8)}}
		>>> a1 = {'b': {1: (1, 'a', 8), 2: (2, 'b', 8), 5: (1, 'a', 8)}}
		>>> a2 = {'b': {1: (1, 'a', 8), 2: [(3, 'B', 80), (4, 'bb', 80)], 10: (10, 't', 80)}}
		>>> mergeit(a2, a1)
		{'b': {1: (1, 'a', 8), 2: [(3, 'B', 80), (4, 'bb', 80), (2, 'b', 8)], 10: (10, 't', 80), 5: (1, 'a', 8)}}
		>>> a1 = {'b': {1: (1, 'a', 8), 2: [(2, 'b', 8), (7, 'r', 8)], 5: (1, 'a', 8)}}
		>>> a2 = {'b': {1: (1, 'a', 8), 2: [(3, 'B', 80), (4, 'bb', 80)], 10: (10, 't', 80)}}
		>>> mergeit(a2, a1)
		{'b': {1: (1, 'a', 8), 2: [(2, 'b', 8), (7, 'r', 8), (3, 'B', 80), (4, 'bb', 80)], 10: (10, 't', 80), 5: (1, 'a', 8)}}
		>>> a1 = {'b': {1: [(1, 'a', 8)], 2: [(2, 'b', 8), (7, 'r', 8)], 5: (1, 'a', 8)}}
		>>> a2 = {'b': {1: (1, 'a', 8), 2: [(3, 'B', 80), (4, 'bb', 80)], 10: (10, 't', 80)}}
		>>> mergeit(a1, a2)
		{'b': {1: (1, 'a', 8), 2: [(2, 'b', 8), (7, 'r', 8), (3, 'B', 80), (4, 'bb', 80)], 10: (10, 't', 80), 5: (1, 'a', 8)}}
		"""

		# first merge blocks ('b' sections)
		n = {}
		for i in m2:
			if m1.has_key(i) and m2[i] != m1[i]:
				if isinstance(m1[i], list) and len(m1[i]) == 1:
					m1[i] = m1[i][0]  # collapse list of len 1
				if isinstance(m2[i], list) and len(m2[i]) == 1:
					m2[i] = m2[i][0]  # collapse list of len 1
				# combine
				if isinstance(m1[i], list) and isinstance(m2[i], list):
					n[i] = m2[i]
					n[i].extend(m1[i]) 
				elif isinstance(m2[i], list):
					n[i] = m2[i]
					n[i] = n[i].append(m1[i])
				elif isinstance(m1[i], list):
					n[i] = m1[i]
					n[i] = n[i].append(m2[i])
				elif m1[i] == m2[i]:
					n[i] = m1[i]
				else:
					n[i] = [m1[i], m2[i]]
			else:
				n[i] = m2[i]
		for i in m1:
			if not n.has_key(i):
				n[i] = m1[i]
		# now n contains the merged blocks.
		m1 = m2 = n
		return m1


class kFINDVAL(ROOT):
	isLeaf = True
	def render_GET(self, request):
		"""
		Return the value, or if we don't have it, the k closest nodes to the
		target ID
		"""
		self.setHeaders(request)
		self.node.DHTtstamp = time.time()
		try:
			required = ('nodeID', 'Ku_e', 'Ku_n', 'port', 'key')
			params = requireParams(request, required)
		except Exception, inst:
			msg = inst.args[0] + " in request received by kFINDVALUE" 
			logger.info(msg)
			request.setResponseCode(http.BAD_REQUEST, "Bad Request")
			return msg 
		else:
			logger.info("received kFINDVALUE request from %s..."
					% params['nodeID'][:10])
			reqKu = {}
			reqKu['e'] = long(params['Ku_e'])
			reqKu['n'] = long(params['Ku_n'])
			reqKu = FludRSA.importPublicKey(reqKu)
			host = getCanonicalIP(request.getClientIP())
			updateNode(self.node.client, self.config, host,
					int(params['port']), reqKu, params['nodeID'])
			fname = self.config.kstoredir+'/'+params['key']	
			if os.path.isfile(fname):
				f = open(fname, "rb")
				logger.info("returning data from kFINDVAL") 
				request.setHeader('nodeID',str(self.config.nodeID))
				request.setHeader('Content-Type','application/x-flud-data')
				d = fdecode(f.read())
				if isinstance(d, dict) and d.has_key(params['nodeID']):
					#print d
					resp = {'b': d['b'], params['nodeID']: d[params['nodeID']]}
					#resp = {'b': d['b']}
					#if d.has_key(params['nodeID']):
					#	resp[params['nodeID']] = d[params['nodeID']]
				else:
					resp = d
				request.write(fencode(resp))
				f.close()
				return ""
			else:
				# return the following if it isn't there.
				logger.info("returning nodes from kFINDVAL for %s" % params['key'])
				request.setHeader('Content-Type','application/x-flud-nodes')
				return "{'id': '%s', 'k': %s}"\
						% (self.config.nodeID,\
						self.config.routing.findNode(fdecode(params['key'])))
		
