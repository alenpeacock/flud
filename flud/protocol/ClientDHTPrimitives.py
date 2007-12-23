"""
ClientDHTPrimitives.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

Primitive client DHT protocol
"""
import time, os, stat, httplib, sys, random, logging
from twisted.web import http, client
from twisted.internet import reactor, threads, defer
from twisted.python import failure
import inspect, pdb

from flud.FludCrypto import FludRSA
import flud.FludkRouting as FludkRouting
from flud.fencode import fencode, fdecode
import flud.FludDefer as FludDefer

import ConnectionQueue
from ClientPrimitives import REQUEST
from FludCommUtil import *

logger = logging.getLogger("flud.client.dht")

# FUTURE: check flud protocol version for backwards compatibility
# XXX: need to make sure we have appropriate timeouts for all comms.
# FUTURE: DOS attacks.  For now, assume that network hardware can filter these 
#      out (by throttling individual IPs) -- i.e., it isn't our problem.  If we
#      want to defend against this at some point, we need to keep track of who
#      is generating requests and then ignore them.
# XXX: might want to consider some self-healing for the kademlia layer, as 
#      outlined by this thread: 
#      http://zgp.org/pipermail/p2p-hackers/2003-August/001348.html (should also
#      consider Zooko's links in the parent to this post).  Basic idea: don't
#      always take the k-closest -- take x random and k-x of the k-closest.
#      Can alternate each round (k-closest / x + k-x-closest) for a bit more
#      diversity (as in "Sybil-resistent DHT routing").
# XXX: right now, calls to updateNode are chained.  Might want to think about
#      doing some of this more asynchronously, so that the recursive parts
#      aren't waiting for remote GETIDs to return before recursing.

"""
The first set of classes (those beginning with 'k') perform [multiple] queries
given a key or key/value pair.  They use the second set of classes (those
beginning with 'SEND'), which perform a single query to a given node.
"""

def serviceWaiting(res, key, pending, waiting):
	# provides a method for calling multiple callbacks on a saved query.
	# add serviceWaiting as a callback before returning, and pass in the result,
	# pending dict and waiting dict.  All deferreds in the waiting dict will
	# be called with the result, the waiting dict will be emptied of those
	# deferreds, and the pending dict will likewise be emptied.
	if waiting.has_key(key):
		for d in waiting[key]:
			#print "offbacking %s" % key
			d.callback(res)
		waiting.pop(key)
	pending.pop(key)
	return res
	
pendingkFindNodes = {}
waitingkFindNodes = {}

class kFindNode:
	"""
	Perform a kfindnode lookup.
	"""
	def __init__(self, node, key):
		if pendingkFindNodes.has_key(key):
			d = defer.Deferred()
			if not waitingkFindNodes.has_key(key):
				waitingkFindNodes[key] = []
			waitingkFindNodes[key].append(d)
			logger.debug("piggybacking on previous kfindnode for %s" % key)
			self.deferred = d
			return
		
		self.node = node
		self.node.DHTtstamp = time.time()
		self.key = key
		self.queried = {}
		self.outstanding = []
		self.pending = []
		self.kclosest = []
		self.abbrvkey = ("%x" % key)[:8]+"..."
		self.abbrv = "(%s%s)" % (self.abbrvkey, str(self.node.DHTtstamp)[-7:])
		self.debugpath = []

		self.deferred = self.startQuery(key)

	def startQuery(self, key):
		# query self first
		kclosest = self.node.config.routing.findNode(key)
		#logger.debug("local kclosest: %s" % kclosest)
		localhost = getCanonicalIP('localhost')
		kd = {'id': self.node.config.nodeID, 'k': kclosest}
		d = self.updateLists(kd, key, localhost, self.node.config.port,
				long(self.node.config.nodeID, 16))
		d.addErrback(self.errkfindnode, key, localhost, self.node.config.port)
		pendingkFindNodes[key] = d
		d.addCallback(serviceWaiting, key, pendingkFindNodes, waitingkFindNodes)
		return d
	
	def sendQuery(self, host, port, id, key):
		self.outstanding.append((host, port, id))
		#d = self.node.client.sendkFindNode(host, port, key)
		d = SENDkFINDNODE(self.node, host, port, key).deferred
		return d

	def updateLists(self, response, key, host, port, closestyet, x=0):
		logger.info("FN: received kfindnode %s response from %s:%d" 
				% (self.abbrv, host, port))
		self.debugpath.append("FN: rec. resp from %s:%d" % (host, port))
		if not isinstance(response, dict):
			# a data value is being returned from findval
			# XXX: moved this bit into findval and call parent for the rest
			if response == None:
				logger.warn("got None from key=%s, %s:%d, x=%d, this usually"
						" means that the host replied None to a findval query" 
						% (key, host, port, x))
			# if we found the fencoded value data, return it
			return defer.succeed(response)
		logger.debug("updateLists(%s)" % response)
		if len(response['k']) == 1 and response['k'][0][2] == key:
			# if we've found the key, don't keep making queries.
			logger.debug("FN: %s:%d found key %s" % (host, port, key))
			self.debugpath.append("FN: %s:%d found key %s" % (host, port, key))
			if response['k'][0] not in self.kclosest:
				self.kclosest.insert(0,response['k'][0])
				self.kclosest = self.kclosest[:FludkRouting.k]
			return defer.succeed(response)

		#for i in response['k']:
		#	print "   res: %s:%d" % (i[0], i[1])
		id = long(response['id'], 16)
		responder = (host, port, id)
		if responder in self.outstanding:
			self.outstanding.remove(responder)
		self.queried[id] = (host, port)

		knodes = response['k']
		for n in knodes:
			if not self.queried.has_key(n[2])\
					and not n in self.pending and not n in self.outstanding:
				self.pending.append((n[0], n[1], n[2]))
			if n not in self.kclosest:
				k = FludkRouting.k
				# XXX: remove self it in the list?
				self.kclosest.append(n)
				self.kclosest.sort(
						lambda a, b: FludkRouting.kCompare(a[2], b[2], key))
				self.kclosest = self.kclosest[:k]

		#for n in self.outstanding:
		#	if n in self.pending:
		#		self.pending.remove(n) # remove anyone we've sent queries to...
		self.pending = list(set(self.pending) - set(self.outstanding))
		for i in self.queried:
			n = (self.queried[i][0], self.queried[i][1], i)
			if n in self.pending:
				self.pending.remove(n) # ...and anyone who has responded.
		
		self.pending.sort(lambda a, b: FludkRouting.kCompare(a[2], b[2], key))

		#print "queried: %s" % str(self.queried)
		#print "outstanding: %s" % str(self.outstanding)
		#print "pending: %s" % str(self.pending)

		return self.decideToContinue(response, key, x)

	def decideToContinue(self, response, key, x):
		##print "x is %s" % str(x)
		##for i in self.kclosest:
		##	print "       kclosest %s" % str(i)
		##for i in self.queried:
		##	print "       queried %s" % str(self.queried[i])
		#if len(filter(lambda x: x not in self.queried, self.kclosest)) <= 0:
		#	print "finishing up at round %d" % x
		#	# XXX: never gets in here...
		#	# XXX: remove anything not in self.kclosest from self.pending
		#	self.pending =\
		#			filter(lambda x: x not in self.kclosest, self.pending)
		#	#self.pending = self.pending[:FludkRouting.k]
		#else:
		#	return self.makeQueries(key, x)

		# this is here so that kFindVal can plug-in by overriding
		return self.makeQueries(key, x)
	
	def makeQueries(self, key, x):
		#print "doing round %d" % x
		self.debugpath.append("FN: doing round %d" % x)
		dlist = []
		for n in self.pending[:(FludkRouting.a - len(self.outstanding))]:
			#print "  querying %s:%d" % (n[0], n[1])
			self.debugpath.append("FN:  querying %s:%d" % (n[0], n[1]))
			d = self.sendQuery(n[0], n[1], n[2], key)
			d.addCallback(self.updateLists, key, n[0], n[1], 
					self.kclosest[0][2], x+1)
			d.addErrback(self.errkfindnode, key, n[0], n[1], 
					raiseException=False)
			dlist.append(d)
		dl = defer.DeferredList(dlist)
		dl.addCallback(self.roundDone, key, x)
		return dl

	def roundDone(self, responses, key, x):
		#print "done %d:" % x
		#print "roundDone: %s" % responses
		if len(self.pending) != 0 or len(self.outstanding) != 0: 
			# should only get here for nodes that don't accept connections
			# XXX: updatenode -- decrease trust
			for i in self.pending:
				logger.debug("FN: %s couldn't contact node %s (%s:%d)" 
						% (self.abbrv, fencode(i[2]), i[0], i[1]))
				self.debugpath.append(
						"FN: %s couldn't contact node %s (%s:%d)" 
						% (self.abbrv, fencode(i[2]), i[0], i[1]))
				for n in self.kclosest:
					if (n[0],n[1],n[2]) == i:
						self.kclosest.remove(n)
		
		logger.info("kFindNode %s terminated successfully after %d queries." 
				% (self.abbrv, len(self.queried)))
		self.debugpath.append("FN: %s terminated successfully after %d queries."
				% (self.abbrv, len(self.queried)))
		self.kclosest.sort(
				lambda a, b: FludkRouting.kCompare(a[2], b[2], key))
		result = {}
		if FludkRouting.k > len(self.kclosest):
			k = len(self.kclosest)
		else:
			k = FludkRouting.k
		result['k'] = self.kclosest[:k]
		#print "result: %s" % result
		#if len(result['k']) > 1:
		#	# if the results (aggregated from multiple responses) contains the
		#	# exact key, just return the correct answer (successful node 
		#	# lookup done).
		#	#print "len(result): %d" % len(result['k'])
		#	#print "result[0][2]: %s %d" % (type(result['k'][0][2]), 
		#	#	result['k'][0][2])
		#	#print "         key: %s %d" % (type(key), key)
		#	if result['k'][0][2] == key:
		#		#print "key matched!"
		#		result['k'] = (result['k'][0],)
		return result

	def errkfindnode(self, failure, key, host, port, raiseException=True):
		logger.info("kFindNode %s request to %s:%d failed -- %s" % (self.abbrv,
			host, port, failure.getErrorMessage()))
		# XXX: updateNode--
		if raiseException:
			return failure 


class kStore(kFindNode):
	"""
	Perform a kStore operation.
	"""

	def __init__(self, node, key, val):
		self.node = node
		self.node.DHTtstamp = time.time()
		self.key = key
		self.val = val
		d = kFindNode(node,key).deferred
		d.addCallback(self.store)
		d.addErrback(self._kStoreErr, None, 0)
		self.deferred = d

	def store(self, knodes):
		knodes = knodes['k']
		if len(knodes) < 1:
			raise RuntimeError("can't complete kStore -- no nodes")
		dlist = []
		for knode in knodes:
			host = knode[0]
			port = knode[1]
			deferred = SENDkSTORE(self.node, host, port, self.key, 
					self.val).deferred
			deferred.addErrback(self._kStoreErr, host, port)
			dlist.append(deferred)
		dl = FludDefer.ErrDeferredList(dlist)
		dl.addCallback(self._kStoreFinished)
		dl.addErrback(self._kStoreErr, None, 0)
		return dl
		
	def _kStoreFinished(self, response):
		#print "_kStoreFinished: %s" % response
		logger.info("kStore finished")
		return ""

	def _kStoreErr(self, failure, host, port):
		logger.info("couldn't store on %s:%d -- %s" 
				% (host, port, failure.getErrorMessage()))
		print "_kStoreErr was: %s" % failure
		# XXX: updateNode--
		return failure


class kFindValue(kFindNode):
	"""
	Perform a kFindValue.
	"""

	def __init__(self, node, key):
		self.done = False
		kFindNode.__init__(self, node, key)

	def startQuery(self, key):
		# query self first.  We override kFindNode.startQuery here so that
		# we don't just return the closest nodeID, but the value itself (if
		# present)
		localhost = getCanonicalIP('localhost')
		d = self.sendQuery(localhost, self.node.config.port, 
				long(self.node.config.nodeID, 16), key)
		d.addCallback(self.updateLists, key, localhost, self.node.config.port, 
				long(self.node.config.nodeID, 16), 0)
		d.addErrback(self.errkfindnode, key, localhost, self.node.config.port)
		return d

	def sendQuery(self, host, port, id, key):
		# We override sendQuery here in order to call sendkFindValue and handle
		# its response
		self.outstanding.append((host, port, id))
		d = SENDkFINDVALUE(self.node, host, port, key).deferred
		d.addCallback(self._handleFindVal, host, port)
		d.addErrback(self.errkfindnode, key, host, port)
		return d

	def _handleFindVal(self, response, host, port):
		if not isinstance(response, dict):
			# stop sending out more queries.
			self.pending = []
			self.done = True
			#print "%s:%d sent value: %s" % (host, port, str(response)[:50])

			#f = {}
			#f['k'] = []
			#f['id'] = "0"
			#f['val'] = response # pass on returned value
			#return f
		else:
			pass
			#print "%s:%d sent kData: %s" % (host, port, response)
		return response

	def decideToContinue(self, response, key, x):
		if self.done:
			#if not response.has_key('val'):
			#	logger.warn("response has no 'val', response is: %s" % response)
			#return response['val']
			return response
		else:
			return self.makeQueries(key, x)
	
	def roundDone(self, responses, key, x):
		self.debugpath.append("FV: roundDone %d" % x)
		if self.done:
			result = {}
			# see if everyone's responses agreed...
			for success, resp in responses:
				# only look at successful non-kData (dict) responses.
				if success and resp != None and not isinstance(resp, dict):
					if result.has_key(resp):
						result[resp] += 1
					else:
						result[resp] = 1
			if len(result) == 0:
				# ... if no one responded, XXX: do something orther than None?
				logger.info("couldn't get any results")
				return None
			elif len(result) == 1:
				# ... if they did, return the result
				return result.keys()[0]
			else:
				# ... otherwise, return the result of the majority
				# (other options include returning all results)
				logger.info("got conflicting results, determining best...")
				quorumResult = None
				bestScore = 0
				for r in result:
					#logger.debug("result %s scored %d" % (r, result[r]))
					if result[r] > bestScore:
						bestScore = result[r]
						quorumResult = r
						#logger.debug("result %s is new best" % r)
				logger.info("returning result %s", fdecode(quorumResult))
				return quorumResult


class SENDkFINDNODE(REQUEST):
	"""
	Makes one request to a node for its k-closest nodes closest to key
	"""
	def __init__(self, node, host, port, key, commandName="nodes"):
		"""
		"""
		logger.info("sending %s (findnode) for %s... to %s:%d" 
				% (commandName, ("%x" % key)[:10], host, port)) 
		self.commandName = commandName
		host = getCanonicalIP(host)
		REQUEST.__init__(self, host, port, node)
		Ku = self.node.config.Ku.exportPublicKey()
		url = 'http://'+host+':'+str(port)+'/'+self.commandName+'/'
		url += fencode(key)
		url += '?nodeID='+str(self.node.config.nodeID)
		url += "&Ku_e="+str(Ku['e'])
		url += "&Ku_n="+str(Ku['n'])
		url += '&port='+str(self.node.config.port)
		self.timeoutcount = 0
		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, node, host, port, key, url))

	def startRequest(self, node, host, port, key, url):
		d = self._sendRequest(node, host, port, key, url)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)

	def _sendRequest(self, node, host, port, key, url):
		factory = getPageFactory(url, 
				headers=self.headers, timeout=kprimitive_to) 
		factory.deferred.addCallback(self._gotResponse, factory,
				node, host, port, key)
		factory.deferred.addErrback(self._errSendk, factory, node, 
				host, port, key, url)
		return factory.deferred
		
	def _gotResponse(self, response, factory, node, host, port, key):
		logger.debug("kfindnode._gotResponse()")
		self._checkStatus(factory.status, response, host, port)
		response = eval(response)
		nID = long(response['id'], 16)
		updateNode(node.client, node.config, host, port, None, nID)
		updateNodes(node.client, node.config, response['k'])
		return response

	def _checkStatus(self, status, response, host, port):
		logger.debug("kfindnode._checkStatus()")
		if eval(status) != http.OK:
			raise failure.DefaultException(self.commandName+" FAILED from "
					+host+":"+str(port)+": received status "+status+", '"
					+response+"'")

	def _errSendk(self, err, factory, node, host, port, key, url):
		if err.check('twisted.internet.error.TimeoutError') or \
				err.check('twisted.internet.error.ConnectionLost'):
			#print "GETID request error: %s" % err.__class__.__name__
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				#print "trying again [#%d]...." % self.timeoutcount
				return self._sendRequest(node, host, port, key, url) 
			else:
				#print "not trying again [#%d]" % self.timeoutcount
				return err
		logger.info("%s to %s failed -- %s" 
				% (self.commandName, self.dest, err.getErrorMessage()))
		# XXX: updateNode--
		return err


class SENDkSTORE(REQUEST):
	"""
	Sends a single kSTORE to the given host:port, with key=val
	"""

	def __init__(self, node, host, port, key, val):
		logger.info("sending kSTORE to %s:%d" % (host, port))
		REQUEST.__init__(self, host, port, node)
		Ku = node.config.Ku.exportPublicKey()
		url = 'http://'+host+':'+str(port)+'/meta/'
		url += fencode(key)+"/"+fencode(val)
		url += '?nodeID='+str(node.config.nodeID)
		url += "&Ku_e="+str(Ku['e'])
		url += "&Ku_n="+str(Ku['n'])
		url += '&port='+str(node.config.port)
		# XXX: instead of a single key/val, protocol will take a series of
		# vals representing the blocks of the coded file and their
		# locations (by nodeID).  The entire thing will be stored under
		# the given key.  Also may need things like signature[s] from 
		# storing node[s], etc.
		#print "in SENDkSTORE.__init__, len(val)=%d" % len(str(val))
		#print "in SENDkSTORE.__init__, len(enc(val))=%d" % len(fencode(val))
		#print "in SENDkSTORE.__init__, len(url)=%d" % len(url)
		self.timeoutcount = 0
		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, host, port, url))

	def startRequest(self, host, port, url):
		d = self._sendRequest(host, port, url)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)
	
	def _sendRequest(self, host, port, url):
		factory = getPageFactory(url,\
				headers=self.headers, method='PUT', timeout=kprimitive_to) 
		self.deferred.addCallback(self._kStoreFinished, host, port)
		self.deferred.addErrback(self._storeErr, host, port, url)
		return factory.deferred
		
	def _kStoreFinished(self, response, host, port):
		logger.info("kSTORE to %s:%d finished" % (host, port))
		return response

	def _storeErr(self, err, host, port, url):
		if err.check('twisted.internet.error.TimeoutError') or \
				err.check('twisted.internet.error.ConnectionLost'):
			#print "GETID request error: %s" % err.__class__.__name__
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				#print "trying again [#%d]...." % self.timeoutcount
				return self._sendRequest(host, port, url) 
			else:
				#print "not trying again [#%d]" % self.timeoutcount
				return err
		logger.info("kSTORE to %s failed: %s" 
				% (self.dest, err.getErrorMessage()))
		# XXX: updateNode--
		return err

class SENDkFINDVALUE(SENDkFINDNODE):
	"""
	Issues a single kFINDVALUE request to host:port for the key.
	If the value is found at host:port, it is returned, otherwise, a
	404 response is received and any errbacks are called.
	"""

	def __init__(self, node, host, port, key):
		SENDkFINDNODE.__init__(self, node, host, port, key, "meta")
		
	def _gotResponse(self, response, factory, node, host, port, key):
		self._checkStatus(factory.status, response, host, port)

		# The following 'if' block is the only thing different from kFINDNODE.
		# If a node returns the value, content-type will be set to x-flud-data
		# and we should grab the data instead of continuing the recursive 
		# search.
		if factory.response_headers.has_key('content-type')\
				and factory.response_headers['content-type']\
						== ['application/x-flud-data']:
			logger.info("received SENDkFINDVALUE data.")
			nID = None
			if factory.response_headers.has_key('nodeid'):
				nID = factory.response_headers['nodeid'][0]
			updateNode(node.client, node.config, host, port, None, nID)
			return response
		
		response = eval(response)
		nID = long(response['id'], 16)
		updateNode(node.client, node.config, host, port, None, nID)

		logger.info("received SENDkFINDVALUE nodes")
		logger.debug("received SENDkFINDVALUE nodes: %s" % response)
		updateNodes(node.client, node.config, response['k'])
		return response

