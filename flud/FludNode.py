#!/usr/bin/python

"""
FludNode.py (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL).

FludNode is the process that runs to talk with other nodes in the flud backup network.
"""

from twisted.internet import reactor, defer
import threading, signal, sys, time, os, random, logging

from flud.FludConfig import FludConfig
from flud.protocol.FludServer import FludServer
from flud.protocol.FludClient import FludClient
from flud.protocol.FludCommUtil import getCanonicalIP
import flud.FludPrimitiveCLI


PINGTIME=60
SYNCTIME=900

class FludNode(object):
	"""
	A node in the flud network.  A node is both a client and a server.  It
	listens on a network accessible port for both DHT and Storage layer
	requests, and it listens on a local port for client interface commands.
	"""
	
	def __init__(self, port=None):
		self._initLogger()
		self.config = FludConfig()
		self.logger.removeHandler(self.screenhandler)
		self.config.load(serverport=port)
		self.client = FludClient(self)
		self.DHTtstamp = time.time()+10

	def _initLogger(self):
		logger = logging.getLogger('flud')
		self.screenhandler = logging.StreamHandler()
		self.screenhandler.setLevel(logging.INFO)
		logger.addHandler(self.screenhandler)
		self.logger = logger

	def pingRandom(self, tstamp):
		return
		# XXX: see pg. 4, Section 2.2 (short) or 2.3 (long) of the Kademlia
		#      paper -- once an hour, each node should check any buckets that
		#      haven't been refreshed and pick a random id within that space
		#      to findnode(id) on, for all buckets.
		if tstamp < self.DHTtstamp: 
			#r = random.randrange(2**256)
			n = self.config.routing.knownExternalNodes()
			if len(n) > 2:
				n1 = random.choice(n)[2]
				n2 = random.choice(n)[2]
				r = (n1+n2)/2
			else:
				r = random.randrange(2**256)
			def badNode(error):
				node.logger.warn("Couldn't ping %s:%s" % 
						(sys.argv[1], sys.argv[2]))
			d = self.client.kFindNode(r)
			d.addErrback(badNode)
		pingtime = random.randrange(PINGTIME/2, PINGTIME)
		reactor.callLater(pingtime, self.pingRandom, time.time())

	def syncConfig(self):
		self.config.save()
		reactor.callLater(SYNCTIME, self.syncConfig)

	def start(self, twistd=False):
		""" starts the reactor in this thread """
		self.webserver = FludServer(self, self.config.port)
		self.logger.log(logging.INFO, "FludServer starting")
		reactor.callLater(1, self.pingRandom, time.time())
		reactor.callLater(random.randrange(10), self.syncConfig)
		if not twistd: 
			reactor.run()

	def run(self):
		""" starts the reactor in its own thread """
		#signal.signal(signal.SIGINT, self.sighandler)
		signal.signal(signal.SIGINT, signal.SIG_DFL)
		signal.signal(signal.SIGTERM, signal.SIG_DFL)
		self.webserver = FludServer(self, self.config.port)
		self.webserver.start()
		# XXX: need to do save out current config every X seconds
		# XXX: need to seperate known_nodes from config, and then update this
		# every X seconds.  only update config when it changes.
	
	def stop(self):
		self.logger.log(logging.INFO, "shutting down FludNode")
		self.webserver.stop()

	def join(self):
		self.webserver.join()

	def sighandler(self, sig, frame):
		self.logger.log(logging.INFO, "handling signal %s" % sig)
	
	def connectViaGateway(self, host, port):

		def refresh(knodes):
			
			def refreshDone(results):
				self.logger.info("bucket refreshes finished: %s" % results)
				print "flud node connected and listening on port %d"\
						% self.config.port
			
			#print "found knodes %s" % knodes
			dlist = []
			for bucket in self.config.routing.kBuckets:
				#if True:
				if bucket.begin <= self.config.routing.node[2] < bucket.end:
					pass
					#print "passed on bucket %x-%s" % (bucket.begin, bucket.end)
				else:
					refreshID = random.randrange(bucket.begin, bucket.end)
					#print "refreshing bucket %x-%x by finding %x" \
					#		% (bucket.begin, bucket.end, refreshID)
					self.logger.info("refreshing bucket %x-%x by finding %x"
							% (bucket.begin, bucket.end, refreshID))
					deferred = self.client.kFindNode(refreshID)
					dlist.append(deferred) 
			dl = defer.DeferredList(dlist)
			dl.addCallback(refreshDone)
			# XXX: do we need to ping newly discovered known nodes?  If not,
			#      we could be vulnerable to a poisoning attack (at first
			#      glance, this attack seems rather impotent...)
			# XXX: need to call refresh about every 60 minutes.  Add a 
			#      reactor.callLater here to do it.
			
		def badGW(error):
			self.logger.warn(error)
			self.logger.warn("Couldn't connect to gateway at %s:%s" % 
					(sys.argv[1], sys.argv[2]))

		self.logger.debug("connectViaGateway %s%d" % (host, port))
		deferred = self.client.sendkFindNode(host, port, 
				self.config.routing.node[2])
		deferred.addCallback(refresh)
		deferred.addErrback(badGW)


"""
Starts up a Flud Node
"""
if __name__ == '__main__':
	from twisted.python import failure
	#import gc
	#gc.set_debug(gc.DEBUG_LEAK)
	#gc.enable()

	if len(sys.argv) == 2:
		# usage was: FludNode.py <listenport>
		node = FludNode(eval(sys.argv[1]))
	elif len(sys.argv) == 4:
		# usage was: FludNode.py <gatewayhost> <gatewayport> <listenport>
		node = FludNode(eval(sys.argv[3]))
	else:
		# usage was: FludNode.py [<gatewayhost> <gatewayport>]
		node = FludNode()

	if len(sys.argv) >= 3:
		# usage was: FludNode.py <gatewayhost> <gatewayport> [listenport]
		node.connectViaGateway(getCanonicalIP(sys.argv[1]), int(sys.argv[2]))

	else:
		print "flud node listening on port %d" % node.config.port

	node.start()

	#node.run()
	#node.join()

