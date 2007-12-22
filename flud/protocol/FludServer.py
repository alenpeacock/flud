"""
FludServer.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

flud server operations
"""

import threading, binascii, time, os, stat, httplib, gc, re, sys, logging, sets
from twisted.web import server, resource, client
from twisted.web.resource import Resource
from twisted.internet import reactor, threads, defer
from twisted.web import http
from twisted.python import threadable, failure

from flud.FludCrypto import FludRSA
import flud.FludkRouting

from ServerPrimitives import *
from ServerDHTPrimitives import *
from LocalPrimitives import *
from FludCommUtil import *
from flud.FludConfig import CommandMap as CommandMap

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
		self.root.putChild('ID', ID(self))     # GET (node identity)
		self.root.putChild('file', FILE(self)) # POST, GET, and DELETE (files)
		self.root.putChild('hash', HASH(self)) # GET (verify op)
		self.root.putChild(CommandMap.PROXY, PROXY(self)) # currently noop
		self.root.putChild(CommandMap.kFINDNODE, kFINDNODE(self))
		self.root.putChild(CommandMap.kFINDVAL, kFINDVAL(self))
		self.root.putChild(CommandMap.kSTORE, kSTORE(self))
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

