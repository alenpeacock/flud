"""
FludCommUtil.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

Communications routines used by both client and server code.
"""
from twisted.web import client
from twisted.internet import reactor, defer
from twisted.python import failure
import binascii, httplib, logging, os, stat, random, socket
import inspect

from flud.FludExceptions import FludException
from flud.FludCrypto import FludRSA, generateRandom
from flud.HTTPMultipartDownloader import HTTPMultipartDownloader

"""
Some constants used by the Flud Protocol classes
"""
PROTOCOL_VERSION = '0.2'
# XXX: when things timeout, bad news.  Unintuitive exceptions spewed.  Make this
#      small and fix all issues.
primitive_to = 3800	# default timeout for primitives
kprimitive_to = primitive_to/2	# default timeout for kademlia primitives
#kprimitive_to = 10	# default timeout for kademlia primitives
transfer_to = 3600 # 10-hr limit on file transfers
MAXTIMEOUTS = 5  # number of times to retry after connection timeout failure
CONNECT_TO = 60
CONNECT_TO_VAR = 5

logger = logging.getLogger('flud.comm')

class BadCASKeyException(failure.DefaultException):
	pass

class NotFoundException(failure.DefaultException):
	pass

class BadRequestException(failure.DefaultException):
	pass


i = 0
"""
Some utility functions used by both client and server.
"""
def updateNodes(client, config, nodes):
	if nodes and not isinstance(nodes, list) and not isinstance(nodes, tuple):
		raise TypeError("updateNodes must be called with node list, tuple,"
				" or kData dict")
	logger.debug("updateNodes(%s)" % nodes)
	for i in nodes:
		host = i[0]
		port = i[1]
		nID = i[2]
		nKu = FludRSA.importPublicKey(i[3])
		updateNode(client, config, host, port, nKu, nID)

updateNodePendingGETID = {}
def updateNode(client, config, host, port, nKu=None, nID=None):
	"""
	Updates this node's view of the given node.  This includes updating
	the known-nodes record, trust, and routing table information
	"""
	def updateNodeFail(failure, host, port):
		logging.getLogger('flud').log(logging.INFO,
				"couldn't get nodeID from %s:%d: %s" % (host, port, failure))

	def callUpdateNode(nKu, client, config, host, port, nID):
		return updateNode(client, config, host, port, nKu, nID)

	if isinstance(nID, long):
		nID = "%064x" % nID

	if nKu is None:
		#print "updateNode, no nKu"
		if nID is None:
			d = client.sendGetID(host, port)
			d.addCallback(callUpdateNode, client, config, host, port, nID)
			d.addErrback(updateNodeFail, host, port)
		else:
			#print "updateNode, no nKu but got a nID"
			if config.nodes.has_key(nID):
				return updateNode(client, config, host, port, 
						FludRSA.importPublicKey(config.nodes[nID]['Ku']), nID)
			elif updateNodePendingGETID.has_key(nID):
				pass
			else:
				#print "updateNode, sending GETID"
				updateNodePendingGETID[nID] = True
				d = client.sendGetID(host, port)
				d.addCallback(callUpdateNode, client, config, host, port, nID)
				d.addErrback(updateNodeFail, host, port)
	elif isinstance(nKu, FludRSA):
		#print "updateNode with nKu"
		if updateNodePendingGETID.has_key(nID):
			del updateNodePendingGETID[nID]
		if nID == None:
			nID = nKu.id()
		elif nID != nKu.id():
			raise ValueError("updateNode: given nID doesn't match given nKu."
					" '%s' != '%s'" % (nID, nKu.id()))
			# XXX: looks like an imposter -- instead of raising, mark host:port
			# pair as bad (trust-- on host:port alone, since we don't know id).
		if config.nodes.has_key(nID) == False:
			config.addNode(nID, host, port, nKu)
		# XXX: trust
		# routing
		node = (host, port, long(nID, 16), nKu.exportPublicKey()['n'])
		replacee = config.routing.updateNode(node)
		#logger.info("knownnodes now: %s" % config.routing.knownNodes())
		#print "knownnodes now: %s" % config.routing.knownNodes()
		if replacee != None:
			logging.getLogger('flud').info(
					"determining if replacement in ktable is needed")
			s = SENDGETID(replacee[0], replacee[1])
			s.addErrback(replaceNode, config.routing, replacee, node)
	else:
		#print "updateNode nKu=%s, type=%s" % (nKu, type(nKu))
		logging.getLogger('flud').warn( 
				"updateNode can't update without a public key or nodeID")
		frame = inspect.currentframe()
		# XXX: try/except here for debugging only
		try:
			stack = inspect.stack()
			for i in stack:
				print "from %s:%d" % (i[1], i[2])
		except:
			print "couldn't get stack trace"
		raise ValueError("updateNode needs an nKu of type FludRSA"
			" (received %s) or an nID of type long or str (received %s)" 
			% (type(nKu), type(nID)))
		# XXX: should really make it impossible to call without one of these...

def replaceNode(error, routing, replacee, replacer):
	routing.replaceNode(replacee, replacer)	
	print "replaced node in ktable"

def requireParams(request, paramNames):
	# Looks for the named parameters in request.  If found, returns
	# a dict of param/value mappings.  If any named parameter is missing,
	# raises an exception
	params = {}
	for i in paramNames:
		try:
			params[i] = request.args[i][0]
		except:
			raise Exception, "missing parameter '"+i+"'" #XXX: use cust Exc
	return params

def getCanonicalIP(IP):
	# if IP is 'localhost' or '127.0.0.1', use the canonical local hostname.
	# (this is mostly useful when multiple clients run on the same host)
	# XXX: could use gethostbyname to get IP addy instead.
	if IP == '127.0.0.1' or IP == 'localhost':
		return socket.getfqdn()
	else:
		return socket.getfqdn(IP)

def getPageFactory(url, contextFactory=None, *args, **kwargs):

	def failedConnect(reason, factory):
		try:
			i = factory.status
			return reason
		except:
			pass
		#logger.warn("couldn't connect to %s:%d in getPageFactory: %s" 
		#		% (factory.host, factory.port, reason))
		#logger.warn("state of factory is %s" % factory)
		#logger.warn("dir() of factory is %s" % dir(factory))
		return reason

	if len(url) >= 16384:
		raise ValueError(
				"Too much data sent: twisted server doesn't appear to"
				" support urls longer than 16384")
	scheme, host, port, path = client._parse(url)
	factory = client.HTTPClientFactory(url, *args, **kwargs)
	factory.deferred.addErrback(failedConnect, factory)
	to = CONNECT_TO+random.randrange(2+CONNECT_TO_VAR)-CONNECT_TO_VAR
	if scheme == 'https':
		from twisted.internet import ssl
		if contextFactory is None:
			contextFactory = ssl.ClientContextFactory()
		reactor.connectSSL(host, port, factory, contextFactory)
	else:
		reactor.connectTCP(host, port, factory, timeout=to)
	return factory

def _dlPageFactory(url, target, factoryClass, contextFactory=None, timeout=None,
		*args, **kwargs):
	scheme, host, port, path = client._parse(url)
	if timeout != None:
		# XXX: do something like http://twistedmatrix.com/pipermail/twisted-python/2003-August/005504.html
		pass
	factory = factoryClass(url, target, *args, **kwargs)
	to = CONNECT_TO+random.randrange(2+CONNECT_TO_VAR)-CONNECT_TO_VAR
	if scheme == 'https':
		from twisted.internet import ssl
		if contextFactory is None:
			contextFactory = ssl.ClientContextFactory()
		reactor.connectSSL(host, port, factory, contextFactory)
	else:
		reactor.connectTCP(host, port, factory, timeout=to)
	return factory

def downloadPageFactory(url, file, contextFactory=None, timeout=None, 
		*args, **kwargs):
	return _dlPageFactory(url, file, client.HTTPDownloader, contextFactory, 
			timeout, *args, **kwargs)

def multipartDownloadPageFactory(url, dir, contextFactory=None, timeout=None,
		*args, **kwargs):
	return _dlPageFactory(url, dir, HTTPMultipartDownloader, contextFactory, 
			timeout, *args, **kwargs)

def fileUpload(host, port, selector, files, form=(), headers={}):
	"""
	Performs a file upload via http.
	host - webserver hostname
	port - webserver listen port
	selector - the request (relative URL)
	files - list of files to upload.  list contains tuples, with the first
		entry as filename/file-like obj and the second as form element name.
		If the first element is a file-like obj, the element will be used as
		the filename.  If the first element is a filename, the filename's
		basename will be used as the filename on the form.  Type will be
		"application/octet-stream"
	form (optional) - a list of pairs of additional name/value form elements 
	    (param/values).
	[hopefully, this method goes away in twisted-web2]
	"""
	# XXX: set timeout (based on filesize?)
	port = int(port)

	rand_bound = binascii.hexlify(generateRandom(13))
	boundary = "---------------------------"+rand_bound
	CRLF = '\r\n'
	body_content_type = "application/octet-stream"
	content_type = "multipart/form-data; boundary="+boundary
	content_length = 0

	H = []
	for (param, value) in form:
		H.append('--' + boundary)
		H.append('Content-Disposition: form-data; name="%s"' % param)
		H.append('')
		H.append('%s' % value)
	form_data = CRLF.join(H)+CRLF
	content_length = content_length + len(form_data)

	fuploads = []
	for file, element in files:
		if file == None:
			file = "/dev/null"   # XXX: not portable 

		if 'read' in dir(file):
			fname = element
			file.seek(0,2)
			file_length = file.tell()
			file.seek(0,0)
		else:
			fname = os.path.basename(file)
			file_length = os.stat(file)[stat.ST_SIZE]

		#logger.info("upload file %s len is %d" % (fname, file_length))

		H = []  # stuff that goes above file data
		T = []  # stuff that goes below file data
		H.append('--' + boundary)
		H.append('Content-Disposition: form-data; name="%s"; filename="%s"' 
				% (element, fname))
		H.append('Content-Type: %s\n' % body_content_type)
		H.append('')
		file_headers = CRLF.join(H)

		content_length = content_length + len(file_headers) + file_length
		fuploads.append((file_headers, file, file_length))

	T.append('--'+boundary+'--')
	T.append('')
	T.append('')
	trailer = CRLF.join(T)
	content_length = content_length + len(trailer)
		
	h = httplib.HTTPConnection(host, port) # XXX: blocking
	h.putrequest('POST', selector)
	for pageheader in headers:
		h.putheader(pageheader, headers[pageheader])
	h.putheader('Content-Type', content_type)
	h.putheader('Content-Length', content_length)
	h.endheaders()

	h.send(form_data)

	for fheader, file, flen in fuploads:
		if 'read' not in dir(file):
			file = open(file, 'r')
		h.send(fheader)
		h.send(file.read(flen)+CRLF) # XXX: blocking
		file.close()

	h.send(trailer)

	return h

class ImposterException(FludException):
	pass

