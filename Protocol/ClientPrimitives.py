"""
ClientPrimitives.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), verison 2.

Primitive client storage protocol
"""

from twisted.web import http, client
from twisted.internet import reactor, threads, defer, error
from twisted.python import failure
from FludCrypto import FludRSA
import FludCrypto
import ConnectionQueue
import time, os, stat, httplib, sys, logging, tarfile
from StringIO import StringIO
from fencode import fencode, fdecode

from FludCommUtil import *

logger = logging.getLogger("flud.client.op")
loggerid = logging.getLogger("flud.client.op.id")
loggerstor = logging.getLogger("flud.client.op.stor")
loggerstoragg = logging.getLogger("flud.client.op.stor.agg")
loggerrtrv = logging.getLogger("flud.client.op.rtrv")
loggerdele = logging.getLogger("flud.client.op.dele")
loggervrfy = logging.getLogger("flud.client.op.vrfy")
loggerauth = logging.getLogger("flud.client.op.auth")

MINSTORSIZE = 512000  # anything smaller than this tries to get aggregated
TARFILE_TO = 5       # timeout for checking aggregated tar files

# FUTURE: check flud protocol version for backwards compatibility
# XXX: need to make sure we have appropriate timeouts for all comms.
# FUTURE: DOS attacks.  For now, assume that network hardware can filter these 
#      out (by throttling individual IPs) -- i.e., it isn't our problem.  If we
#      want to defend against this at some point, we need to keep track of who
#      is generating requests and then ignore them.
# XXX: might want to consider some self-healing for the kademlia layer, as 
#      outlined by this thread: 
#      http://zgp.org/pipermail/p2p-hackers/2003-August/001348.html (should also
#      consider Zooko's links in the parent to this post)
# XXX: disallow requests to self.

class REQUEST(object):
	"""
	This is a parent class for generating http requests that follow the 
	FludProtocol.
	"""
	def __init__(self, host, port, node=None):
		"""
		All children should inherit.  By convention, subclasses should 
		create a URL and attempt to retrieve it in the constructor.
		@param node the requestor's node object
		"""
		self.host = host
		self.port = port
		self.dest = "%s:%d" % (host, port)
		if node:
			self.node = node
			self.config = node.config
		self.headers = {'Fludprotocol': fludproto_ver,
				'User-Agent': 'FludClient 0.1'}


class SENDGETID(REQUEST):

	def __init__(self, node, host, port):
		"""
		Send a request to retrive the node's ID.  This is a reciprocal
		request -- must send my own ID in order to get one back.
		"""
		host = getCanonicalIP(host)
		REQUEST.__init__(self, host, port, node)
		Ku = self.node.config.Ku.exportPublicKey()
		url = "http://"+host+":"+str(port)+"/ID?"
		url += 'nodeID='+str(self.node.config.nodeID)
		url += '&port='+str(self.node.config.port)
		url += "&Ku_e="+str(Ku['e'])
		url += "&Ku_n="+str(Ku['n'])
		#self.nKu = {}
		self.timeoutcount = 0
		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, node, host, port, url))

	def startRequest(self, node, host, port, url):
		loggerid.info("sending SENDGETID to %s" % self.dest)
		d = self._sendRequest(node, host, port, url)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)
		d.addErrback(self._errID, node, host, port, url)

	def _sendRequest(self, node, host, port, url):
		factory = getPageFactory(url, timeout=primitive_to,
				headers=self.headers)
		d2 = factory.deferred
		d2.addCallback(self._getID, factory, host, port)
		d2.addErrback(self._errID, node, host, port, url)
		return d2
		
	def _getID(self, response, factory, host, port):
		loggerid.debug( "received ID response: %s" % response)
		if not hasattr(factory, 'status'):
			raise failure.DefaultException(
					"SENDGETID FAILED: no status in factory")
		if eval(factory.status) != http.OK:
			raise failure.DefaultException("SENDGETID FAILED to "+self.dest+": "
					+"server sent status "+factory.status+", '"+response+"'")
		try:
			nKu = {}
			nKu = eval(response)
			nKu = FludRSA.importPublicKey(nKu)
			loggerid.info("SENDGETID PASSED to %s" % self.dest)
			updateNode(self.node.client, self.config, host, port, nKu)
			return nKu
		except:
			raise failure.DefaultException("SENDGETID FAILED to "+self.dest+": "
					+"received response, but it did not contain valid key")

	def _errID(self, err, node, host, port, url):
		if err.check('twisted.internet.error.TimeoutError') or \
				err.check('twisted.internet.error.ConnectionLost'):
			#print "GETID request error: %s" % err.__class__.__name__
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				#print "trying again [#%d]...." % self.timeoutcount
				return self._sendRequest(node, host, port, url) 
			else:
				#print "not trying again [#%d]" % self.timeoutcount
				return err
		# XXX: updateNode
		#print "_errID: %s" % err
		#print "_errID: %s" % str(err.stack)
		return err


# XXX: either 1) produce filekey here or 2) send it in as part of API
#      (similar fixes for SENDRETRIEVE and VERIFY)?  Currently filekey is
#      chosen by caller, and is simply the filename.
class SENDSTORE(REQUEST):

	def __init__(self, nKu, node, host, port, datafile, metadata=None, fsize=0):
		"""
		Try to upload a file.
		"""
		host = getCanonicalIP(host)
		REQUEST.__init__(self, host, port, node)

		loggerstor.info("sending STORE request to %s" % self.dest)
		if not fsize:
			fsize = os.stat(datafile)[stat.ST_SIZE]
		Ku = self.node.config.Ku.exportPublicKey()
		params = [('nodeID', self.node.config.nodeID),
				('Ku_e', str(Ku['e'])),
				('Ku_n', str(Ku['n'])),
				('port', str(self.node.config.port)),
				('filekey', os.path.basename(datafile)),
				('size', str(fsize))]
		self.timeoutcount = 0

		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, self.headers, nKu, host, port, 
				datafile, metadata, params, True))
		#self.deferred = self._sendRequest(self.headers, nKu, host, port,
		#		datafile, params, True)

	def startRequest(self, headers, nKu, host, port, datafile, metadata,
			params, skipFile):
		d = self._sendRequest(headers, nKu, host, port, datafile, metadata, 
				params, skipFile)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)

	def _sendRequest(self, headers, nKu, host, port, datafile, metadata,
			params, skipfile=False):
		"""
		skipfile - set to True if you want to send everything but file data
		(used to send the unauthorized request before responding to challenge)
		"""
		if skipfile:
			files = [(None, 'filename')]
		elif metadata:
			metakey = metadata[0]
			params.append(('metakey', metakey))
			metafile = metadata[1]
			files = [(datafile, 'filename'), (metafile, 'meta')]
		else:
			files = [(datafile, 'filename')]
		deferred = threads.deferToThread(fileUpload, host, port, 
				'/STORE', files, params, headers=self.headers)
		deferred.addCallback(self._getSendStore, nKu, host, port, datafile,
				metadata, params, self.headers)
		deferred.addErrback(self._errSendStore, 
				"Couldn't upload file %s to %s:%d" % (datafile, host, port),
				self.headers, nKu, host, port, datafile, metadata, params)
		return deferred

	def _getSendStore(self, httpconn, nKu, host, port, datafile, metadata,
			params, headers):
		"""
		Check the response for status. 
		"""
		deferred2 = threads.deferToThread(httpconn.getresponse)
		deferred2.addCallback(self._getSendStore2, httpconn, nKu, host, port, 
				datafile, metadata, params, headers)
		deferred2.addErrback(self._errSendStore, "Couldn't get response", 
				headers, nKu, host, port, datafile, metadata, params, httpconn)
		return deferred2

	def _getSendStore2(self, response, httpconn, nKu, host, port, datafile,
			metadata, params, headers):
		httpconn.close()
		if response.status == http.UNAUTHORIZED:
			loggerstor.info("SENDSTORE unauthorized, sending credentials")
			challenge = response.reason
			d = answerChallengeDeferred(challenge, self.node.config.Kr,
					self.node.config.groupIDu, nKu.id(), headers)
			d.addCallback(self._sendRequest, nKu, host, port, datafile, 
					metadata, params)
			d.addErrback(self._errSendStore, "Couldn't answerChallenge", 
					headers, nKu, host, port, datafile, metadata, params, 
					httpconn)
			return d
		elif response.status == http.CONFLICT:
			result = response.read()
			# XXX: client should check key before ever sending request
			raise BadCASKeyException("%s %s" 
					% (response.status, response.reason))
		elif response.status != http.OK:
			result = response.read()
			raise failure.DefaultException( 
					"received %s in SENDSTORE response: %s"
					% (response.status, result))
		else:
			result = response.read()
			updateNode(self.node.client, self.config, host, port, nKu)
			loggerstor.info("received SENDSTORE response from %s: %s" 
					% (self.dest, str(result)))
			return result

	def _errSendStore(self, err, msg, headers, nKu, host, port,
			datafile, metadata, params, httpconn=None):
		if err.check('socket.error'):
			#print "SENDSTORE request error: %s" % err.__class__.__name__
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				print "trying again [#%d]...." % self.timeoutcount
				return self._sendRequest(headers, nKu, host, port, datafile, 
						metadata, params)
			else:
				print "Maxtimeouts exceeded: %d" % self.timeoutcount
		elif err.check(BadCASKeyException):
			pass
		else:
			print "%s: unexpected error in SENDSTORE: %s" % (msg, 
					str(err.getErrorMessage()))
		# XXX: updateNode
		if httpconn:
			httpconn.close()
		#loggerstor.info(msg+": "+err.getErrorMessage())
		return err


aggDeferredMap = {}  # a map of maps, containing deferreds.  The deferred for
					 # file 'x' in tarball 'y' is accessed as
					 # aggDeferredMap['y']['x']
aggTimeoutMap = {}   # a map of timout calls for a tarball.  The timeout for
                     # tarball 'y' is stored in aggTimeoutMap['y']
class AggregateStore:

	# XXX: if multiple guys store the same file, we're going to get into bad
	# cb state (the except clause in errbackTarfiles).  Need to catch this
	# as it happens... (this happens e.g. for small files with the same
	# filehash, e.g, 0-byte files, file copies etc).  Should fix this in
	# FludClient -- non-agg store has a similar problem (encoded file chunks
	# get deleted out from under successive STOR ops for the same chunk, i.e.
	# from two concurrent STORs of the same file contents)
	def __init__(self, nKu, node, host, port, datafile, metadata):
		tarfilename = os.path.join(node.config.clientdir,nKu.id())\
				+'-'+host+'-'+str(port)+".tar"
		loggerstoragg.debug("tarfile name is %s" % tarfilename)
		if not os.path.exists(tarfilename) \
				or not aggDeferredMap.has_key(tarfilename):
			loggerstoragg.debug("creating tarfile %s to append %s" 
					% (tarfilename, datafile))
			tar = tarfile.open(tarfilename, "w")
			tarfileTimeout = reactor.callLater(TARFILE_TO, self.sendTar,  
					tarfilename, nKu, node, host, port)
			aggDeferredMap[tarfilename] = {}
			aggTimeoutMap[tarfilename] = tarfileTimeout
		else:
			loggerstoragg.debug("opening tarfile %s to append %s"
					% (tarfilename, datafile))
			tar = tarfile.open(tarfilename, "a")
			
		tar.add(datafile, os.path.basename(datafile))

		if metadata:
			metafilename = "%s.%s.meta" % (os.path.basename(datafile), 
					metadata[0])
			loggerstoragg.debug("metadata filename is %s" % metafilename)
			try:
				if isinstance(metadata[1], StringIO):
					loggerstoragg.debug("metadata is StringIO")
					tinfo = tarfile.TarInfo(metafilename)
					metadata[1].seek(0,2)
					tinfo.size = metadata[1].tell()
					metadata[1].seek(0,0)
					tar.addfile(tinfo, metadata[1])
				else:
					loggerstoragg.debug("metadata is file")
					tar.add(metadata[1], metafilename) 
			except:
				import traceback
				loggerstoragg.debug("exception while adding metadata to"
						" tarball")
				print sys.exc_info()[2]
				traceback.print_exc()

		tar.close()
		loggerstoragg.debug("prepping deferred")
		# XXX: (re)set timeout for tarfilename
		self.deferred = defer.Deferred()
		loggerstoragg.debug("adding deferred on %s for %s" 
				% (tarfilename, datafile))
		aggDeferredMap[tarfilename][os.path.basename(datafile)] = self.deferred
		self.resetTimeout(aggTimeoutMap[tarfilename], tarfilename)

	def resetTimeout(self, timeoutFunc, tarball):
		loggerstoragg.debug("in resetTimeout...")
		if timeoutFunc.active():
			#timeoutFunc.reset(TARFILE_TO)
			if os.stat(tarball)[stat.ST_SIZE] < MINSTORSIZE:
				loggerstoragg.debug("...reset")
				timeoutFunc.reset(TARFILE_TO)
				return
		loggerstoragg.debug("...didn't reset")
		
	def sendTar(self, tarball, nKu, node, host, port):
		loggerstoragg.info(
				"aggregation op triggered, sending tarfile %s to %s:%d" 
				% (tarball, host, port))
		self.deferred = SENDSTORE(nKu, node, host, port, tarball).deferred
		self.deferred.addCallback(self.callbackTarfiles, tarball)
		self.deferred.addErrback(self.errbackTarfiles, tarball)

	def callbackTarfiles(self, result, tarball):
		loggerstoragg.debug("callbackTarfiles")
		tar = tarfile.open(tarball, "r:")
		cbs = []
		try: 
			for tarinfo in tar:
				if tarinfo.name[-5:] != '.meta':
					loggerstoragg.debug("callingback for %s in %s" % 
							(tarinfo.name, tarball))
					d = aggDeferredMap[tarball].pop(tarinfo.name) 
					cbs.append(d)
		except KeyError:
			loggerstoragg.warn("aggDeferredMap has keys: %s" 
					% str(aggDeferredMap.keys()))
			loggerstoragg.warn("aggDeferredMap[%s] has keys: %s" % (tarball, 
					str(aggDeferredMap[tarball].keys())))
		tar.close()
		loggerstoragg.debug("deleting tarball")
		os.remove(tarball)
		for cb in cbs:
			cb.callback(result)

	def errbackTarfiles(self, failure, tarball):
		loggerstoragg.debug("errbackTarfiles")
		tar = tarfile.open(tarball, "r:")
		cbs = []
		try: 
			for tarinfo in tar:
				loggerstoragg.debug("erringback for %s in %s" % 
						(tarinfo.name, tarball))
				d = aggDeferredMap[tarball].pop(tarinfo.name) 
				cbs.append(d)
		except KeyError:
			loggerstoragg.warn("aggDeferredMap has keys: %s" 
					% str(aggDeferredMap.keys()))
			loggerstoragg.warn("aggDeferredMap[%s] has keys: %s" % (tarball, 
					str(aggDeferredMap[tarball].keys())))
		tar.close()
		loggerstoragg.debug("deleting tarball")
		#os.remove(tarball)
		for cb in cbs:
			cb.errback(failure)

class SENDRETRIEVE(REQUEST):

	def __init__(self, nKu, node, host, port, filekey):
		"""
		Try to download a file.
		"""
		host = getCanonicalIP(host)
		REQUEST.__init__(self, host, port, node)

		loggerrtrv.info("sending RETRIEVE request to %s:%s" % (host, str(port)))
		Ku = self.node.config.Ku.exportPublicKey()
		url = 'http://'+host+':'+str(port)+'/RETRIEVE/'+filekey+'?'
		url += 'nodeID='+str(self.node.config.nodeID)
		url += '&port='+str(self.node.config.port)
		url += "&Ku_e="+str(Ku['e'])
		url += "&Ku_n="+str(Ku['n'])
		filename = self.node.config.clientdir+'/'+filekey
		self.timeoutcount = 0

		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, self.headers, nKu, host, port, 
			url, filename))

	def startRequest(self, headers, nKu, host, port, url, filename):
		#print "doing RET: %s" % filename
		d = self._sendRequest(headers, nKu, host, port, url, filename)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)

	def _sendRequest(self, headers, nKu, host, port, url, filename):
		factory = downloadPageFactory(url, filename,
				headers=headers, timeout=transfer_to)
		deferred = factory.deferred
		deferred.addCallback(self._getSendRetrieve, nKu, host, port, factory)
		deferred.addErrback(self._errSendRetrieve, nKu, host, port, factory, 
				url, filename, headers)
		return deferred

	def _getSendRetrieve(self, response, nKu, host, port, factory):
		if eval(factory.status) == http.OK:
			# response is None, since it went to file (if a server error
			# occured, it may be printed in this file)
			# XXX: need to check that file hashes to key! If we don't do this,
			#      malicious nodes can corrupt entire files without detection!
			result = "received SENDRETRIEVE response"
			loggerrtrv.info(result)
			updateNode(self.node.client, self.config, host, port, nKu)
			return result
		else:
			raise failure.DefaultException("SENDRETRIEVE FAILED: "
					+"server sent status "+factory.status+", '"+response+"'")

	def _errSendRetrieve(self, err, nKu, host, port, factory, url, filename, 
			headers):
		if err.check('twisted.internet.error.TimeoutError') or \
				err.check('twisted.internet.error.ConnectionLost'): #or \
				#err.check('twisted.internet.error.ConnectBindError'):
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				#print "RETR trying again [#%d]..." % self.timeoutcount
				#print "RETR trying again [#%d]....%s" % (self.timeoutcount, 
				#		filename)
				return self._sendRequest(headers, nKu, host, port, url, 
						filename)
			else:
				#print "RETR timeout exceeded: %d" % self.timeoutcount
				pass
		elif hasattr(factory, 'status') and \
				eval(factory.status) == http.UNAUTHORIZED:
			loggerrtrv.info("SENDRETRIEVE unauthorized, sending credentials")
			challenge = err.getErrorMessage()[4:]
			d = answerChallengeDeferred(challenge, self.node.config.Kr,
					self.node.config.groupIDu, nKu.id(), headers)
			d.addCallback(self._sendRequest, nKu, host, port, url, filename)
			#d.addErrback(self._errSendRetrieve, nKu, host, port, factory,
			#		url, filename, headers)
			return d
			#extraheaders = answerChallenge(challenge, self.node.config.Kr,
			#		self.node.config.groupIDu, nKu.id(), self.headers)
			#return self._sendRequest(nKu, host, port, url, filename, 
			#		extraheaders)
		# XXX: these remaining else clauses are really just for debugging...
		elif hasattr(factory, 'status'):
			if eval(factory.status) == http.NOT_FOUND:
				err = NotFoundException(err)
			elif eval(factory.status) == http.BAD_REQUEST:
				err = BadRequestException(err)
		elif err.check('twisted.internet.error.ConnectionRefusedError'):
			pass # fall through to return err
		else:
			print "non-timeout, non-UNAUTH RETR request error: %s" % err
		# XXX: updateNode
		loggerrtrv.info("SENDRETRIEVE failed")
		raise err

class SENDDELETE(REQUEST):

	def __init__(self, nKu, node, host, port, filekey):
		"""
		Try to delete a file.
		"""
		host = getCanonicalIP(host)
		REQUEST.__init__(self, host, port, node)

		loggerdele.info("sending DELETE request to %s:%s" % (host, str(port)))
		Ku = self.node.config.Ku.exportPublicKey()
		url = 'http://'+host+':'+str(port)+'/DELETE/'+filekey+'?'
		url += 'nodeID='+str(self.node.config.nodeID)
		url += '&port='+str(self.node.config.port)
		url += "&Ku_e="+str(Ku['e'])
		url += "&Ku_n="+str(Ku['n'])
		self.timeoutcount = 0

		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

	def startRequest(self, headers, nKu, host, port, url):
		d = self._sendRequest(headers, nKu, host, port, url)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)

	def _sendRequest(self, headers, nKu, host, port, url):
		factory = getPageFactory(url, headers=headers, timeout=primitive_to)
		deferred = factory.deferred
		deferred.addCallback(self._getSendDelete, nKu, host, port, factory)
		deferred.addErrback(self._errSendDelete, nKu, host, port, factory, url,
				headers)
		return deferred

	def _getSendDelete(self, response, nKu, host, port, factory):
		if eval(factory.status) == http.OK:
			loggerdele.info("received SENDDELETE response")
			updateNode(self.node.client, self.config, host, port, nKu)
			return response
		else:
			# XXX: updateNode
			raise failure.DefaultException("SENDDELETE FAILED: "
					+"server sent status "+factory.status+", '"+response+"'")

	def _errSendDelete(self, err, nKu, host, port, factory, url, headers):
		if err.check('twisted.internet.error.TimeoutError') or \
				err.check('twisted.internet.error.ConnectionLost'):
			#print "DELETE request error: %s" % err.__class__.__name__
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				#print "trying again [#%d]...." % self.timeoutcount
				return self._sendRequest(headers, nKu, host, port, url) 
		elif hasattr(factory, 'status') and \
				eval(factory.status) == http.UNAUTHORIZED:
			loggerdele.info("SENDDELETE unauthorized, sending credentials")
			challenge = err.getErrorMessage()[4:]
			d = answerChallengeDeferred(challenge, self.node.config.Kr,
					self.node.config.groupIDu, nKu.id(), headers)
			d.addCallback(self._sendRequest, nKu, host, port, url)
			d.addErrback(self._errSendDelete, nKu, host, port, factory,
					url, headers)
			return d
		elif hasattr(factory, 'status'):
			# XXX: updateNode
			loggerdele.info("SENDDELETE failed")
			if eval(factory.status) == http.NOT_FOUND:
				err = NotFoundException(err)
			elif eval(factory.status) == http.BAD_REQUEST:
				err = BadRequestException(err)
			raise err
		return err

class SENDVERIFY(REQUEST):

	def __init__(self, nKu, node, host, port, filename, offset, length):
		"""
		Try to verify a file.
		"""
		host = getCanonicalIP(host)
		REQUEST.__init__(self, host, port, node)

		filekey = os.path.basename(filename) # XXX: filekey should be hash
		loggervrfy.info("sending VERIFY request to %s:%s" % (host, str(port)))
		Ku = self.node.config.Ku.exportPublicKey()
		url = 'http://'+host+':'+str(port)+'/VERIFY/'+filekey+'?'
		url += 'nodeID='+str(self.node.config.nodeID)
		url += '&port='+str(self.node.config.port)
		url += "&Ku_e="+str(Ku['e'])
		url += "&Ku_n="+str(Ku['n'])
		url += "&offset="+str(offset)
		url += "&length="+str(length)
		self.timeoutcount = 0

		if not isinstance(nKu, FludRSA):
			raise ValueError("must pass in a FludRSA as nKu to SENDVERIFY")

		self.deferred = defer.Deferred()
		ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

	def startRequest(self, headers, nKu, host, port, url):
		#loggervrfy.debug("*Doing* VERIFY Request %s" % port)
		d = self._sendRequest(headers, nKu, host, port, url)
		d.addBoth(ConnectionQueue.checkWaiting)
		d.addCallback(self.deferred.callback)
		d.addErrback(self.deferred.errback)

	def _sendRequest(self, headers, nKu, host, port, url):
		loggervrfy.debug("in VERIFY sendReq %s" % port)
		factory = getPageFactory(url, headers=headers, timeout=primitive_to)
		deferred = factory.deferred
		deferred.addCallback(self._getSendVerify, nKu, host, port, factory)
		deferred.addErrback(self._errSendVerify, nKu, host, port, factory, url,
				headers)
		return deferred

	def _getSendVerify(self, response, nKu, host, port, factory):
		loggervrfy.debug("got vrfy response")
		if eval(factory.status) == http.OK:
			loggervrfy.info("received SENDVERIFY response")
			updateNode(self.node.client, self.config, host, port, nKu)
			return response
		else:
			# XXX: updateNode
			loggervrfy.debug("received non-OK SENDVERIFY response")
			raise failure.DefaultException("SENDVERIFY FAILED: "
					+"server sent status "+factory.status+", '"+response+"'")

	def _errSendVerify(self, err, nKu, host, port, factory, url, headers):
		loggervrfy.debug("got vrfy err")
		if err.check('twisted.internet.error.TimeoutError') or \
				err.check('twisted.internet.error.ConnectionLost'):
			#print "VERIFY request error: %s" % err.__class__.__name__
			self.timeoutcount += 1
			if self.timeoutcount < MAXTIMEOUTS:
				#print "trying again [#%d]...." % self.timeoutcount
				return self._sendRequest(headers, nKu, host, port, url) 
		elif hasattr(factory, 'status') and \
				eval(factory.status) == http.UNAUTHORIZED:
			loggervrfy.info("SENDVERIFY unauthorized, sending credentials")
			challenge = err.getErrorMessage()[4:]
			d = answerChallengeDeferred(challenge, self.node.config.Kr,
					self.node.config.groupIDu, nKu.id(), headers)
			d.addCallback(self._sendRequest, nKu, host, port, url)
			d.addErrback(self._errVerify, nKu, host, port, factory,
					url, headers, challenge)
			#d.addErrback(self._errSendVerify, nKu, host, port, factory,
			#		url, headers)
			return d
		elif hasattr(factory, 'status'):
			# XXX: updateNode
			loggervrfy.info("SENDVERIFY failed: %s" % err.getErrorMessage())
			if eval(factory.status) == http.NOT_FOUND:
				err = NotFoundException(err)
			elif eval(factory.status) == http.BAD_REQUEST:
				err = BadRequestException(err)
		raise err

	def _errVerify(self, err, nKu, host, port, factory, url, headers,
			challenge):
		# we can get in here after storing the same file as another node when
		# that data is stored in tarballs under its ID.  It was expected that
		# this would be caught up in _getSendVerify... figure out why it isn't.
		loggervrfy.debug("factory status=%s" % factory.status)
		loggervrfy.debug("couldn't answer challenge from %s:%d, WHOOPS: %s" 
				% (host, port, err.getErrorMessage()))
		loggervrfy.debug("challenge was: '%s'" % challenge)
		return err


def answerChallengeDeferred(challenge, Kr, groupIDu, sID, headers): 
	return threads.deferToThread(answerChallenge, challenge, Kr, groupIDu, sID,
			headers)

def answerChallenge(challenge, Kr, groupIDu, sID, headers={}):
	loggerauth.debug("got challenge: '%s'" % challenge)
	sID = binascii.unhexlify(sID)
	challenge = (fdecode(challenge),)
	response = fencode(Kr.decrypt(challenge))
	# XXX: RSA.decrypt won't restore leading 0's.  This causes
	#      some challenges to fail when they shouldn't -- solved for now
	#      on the server side by generating non-0 leading challenges.
	loggerauth.debug("decrypted challenge to %s" % response)
	responseID = fdecode(response)[:len(sID)]
	loggerauth.debug("  response id: %s" % fencode(responseID))
	if responseID != sID:
		# fail the op.
		# If we don't do this, we may be allowing the server to build a
		# dictionary useful for attack.  The attack is as follows: node A
		# (server) collects a bunch of un-IDed challenge/response pairs by
		# issuing challenges to node B (client).  Then node A uses those
		# responses to pose as B to some other server C.  This sounds
		# farfetched, in that such a database would need to be huge, but in
		# reality, such an attack can happen in real-time, with node A
		# simultaneously serving requests from B, relaying challenges from C to
		# B, and then responding with B's responses to C to gain resources
		# there as an imposter.  The ID string prevents this attack.

		# XXX: trust-- (must go by ip:port, since ID could be innocent)
		raise ImposterException("node %s is issuing invalid challenges --"
				" claims to have id=%s" % (fencode(sID), fencode(responseID)))
	response = fdecode(response)[len(sID):]
	loggerauth.debug("  challenge response: '%s'" % fencode(response))
	response = fencode(response)+":"+groupIDu
	loggerauth.debug("response:groupIDu=%s" % response)
	response = binascii.b2a_base64(response)
	loggerauth.debug("b64(response:groupIDu)=%s" % response)
	response = "Basic %s" % response
	headers['Authorization'] = response
	return headers 
