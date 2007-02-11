"""
FludServer.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL).

flud server ops
"""

from twisted.web import server, resource, client
from twisted.web.resource import Resource
from twisted.internet import reactor, threads, defer
from twisted.protocols import http
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

"""
Justifications for using http as a transport for Flud:
	1- Stateless is good.  Http is stateless. Maintaining a lot of state about
	   servers/clients is almost universally considered problematic when
	   designing distributed systems (or at least something to avoid whenever
	   possible).  Http helps enforce this idea, and discourages the use of
	   complex, long-standing open connections.  In short, this choice is one
	   that helps encourage simplification in the design.  All Flud messages
	   consist of a request/response pair, nothing more.  Http keepalive is
	   also available for efficiently doing multiple stateless comms between
	   nodes. (note: it is true that some requests, STORE, RETRIEVE, VERIFY, 
	   generate additional requests back to the original requestor.  But
	   we will still consider this stateless because the asynchronous framework
	   provides us with Deferreds.  Each request/response pair can timeout on
	   its own without us having to keep track of any state.)
	2- Http has the advantage of being able to operate transparently through
	   firewalls, proxies, and NAT'ed networks.  We get this for free.
	3- Nice mechanisms in twisted-python (and most other languages) for 
	   handling http.  Quick prototyping easy.
	4- Stealth.  Use of http makes filtering and blocking more difficult for
	   those wishing to do so.  In addition, Flud has customizable protocol
	   keywords, making it a bit of a moving target for custom filters (though
	   it will likely never be impossible to filter flud).  Taken together,
	   these features might appear to be ISP unfriendly -- but that isn't the
	   intent.  The intent is simply to make flud as available and useful to
	   end users as possible, and if some entity targets flud for whatever
	   reason, flud can strike back with its own countermeasures.  This also
	   makes flud traffic more difficult for a third party to sniff/track --
	   ideally its traffic will be mostly hidden in the bulk of other web
	   traffic, and its extraction (while possible) will require more work.  
	5- Unlike RCP (and its brethren), HTTP doesn't attempt to hide network
	   communications from the programmer.  HTTP admits, loudly, that 
	   communicating with a remote host is intrinsically different than 
	   calling a local procedure.  This is truth.  This is good.
	6- Security.  HTTP has acquired many mechanisms for access control and
	   authentication.  If we need those mechanisms, we can simply use them.
	   There is no need to re-invent these by using some other transport that
	   lacks them.
	7- We're lazy.  Use of http means we don't have to reinvent any of the 
	   above mechanisms.  Laziness is good when you can get away with it,
	   because it means you can spend your time doing something more useful.
"""

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

