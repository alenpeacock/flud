"""
FludServer.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

flud server operations
"""

from twisted.web import server, resource, client
from twisted.web.resource import Resource
from twisted.internet import reactor, threads, defer
from twisted.web import http
from twisted.python import threadable, failure
from FludCrypto import FludRSA
import FludCrypto
import FludkRouting
import threading, binascii, time, os, stat, httplib, gc, re, sys, logging, sets

from ServerPrimitives import *
from ServerDHTPrimitives import *
from LocalPrimitives import *
from FludCommUtil import *

threadable.init()

class FludServer(threading.Thread):
	"""
	This class runs the webserver, responding to all requests.
	"""
	def __init__(self, node, port):
		threading.Thread.__init__(self)
		self.port = port
		self.node = node
		self.clientport = node.config.clientport
		self.logger = node.logger
		self.root = ROOT(self)
		commandmap = node.config.commandmap
		self.root.putChild(commandmap['ID'], ID(self))
		self.root.putChild(commandmap['STORE'], STORE(self))
		self.root.putChild(commandmap['RETRIEVE'], RETRIEVE(self))
		self.root.putChild(commandmap['VERIFY'], VERIFY(self))
		self.root.putChild(commandmap['PROXY'], PROXY(self))
		self.root.putChild(commandmap['DELETE'], DELETE(self))
		self.root.putChild(commandmap['kFINDNODE'], kFINDNODE(self))
		self.root.putChild(commandmap['kFINDVAL'], kFINDVAL(self))
		self.root.putChild(commandmap['kSTORE'], kSTORE(self))
		self.site = server.Site(self.root)
		reactor.listenTCP(self.port, self.site)
		reactor.listenTCP(self.clientport, LocalFactory(node), 
				interface="127.0.0.1")
		#print "FludServer will listen on port %d, local client on %d"\
		#		% (self.port, self.clientport)
		self.logger.log(logging.INFO,\
				"FludServer will listen on port %d, local client on %d" 
				% (self.port, self.clientport))
		
	def run(self):
		self.logger.log(logging.INFO, "FludServer starting")
		return reactor.run(installSignalHandlers=0)

	def stop(self):
		self.logger.log(logging.INFO, "FludServer stopping")
		reactor.stop()

