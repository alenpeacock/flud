#!/usr/bin/python
"""
LocalClient.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

LocalClient provides client functions which can be called to send commands to
a local FludNode instance.
"""

import sys, os, time
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.python import threadable
threadable.init()

from flud.fencode import fencode, fdecode

from LocalPrimitives import *

logger = logging.getLogger("flud.local.client")

opTimeout = 1200
VALIDOPS = LocalProtocol.commands.keys() + ['AUTH', 'DIAG']

# XXX: print commands should either be raised, or put on factory.msgs

class LocalClient(LineReceiver):
	MAX_LENGTH = 300000
	auth=False
	
	def connectionMade(self):
		logger.debug("connection est.")
		self.auth=False
		self.sendLine("AUTH?")

	def lineReceived(self, line):
		logger.debug("received line '%s'" % line)
		command = line[0:4]
		if not command in VALIDOPS:
			print "error: invalid command op ('%s')-- "\
					" are you trying to connect to the wrong port"\
					" (local client port is usually external port + 500)?"\
					% command
			return None
		status = line[4]
		data = line[5:]
		if not self.auth:
			if command == "AUTH" and status == '?':
				# got challenge, send response
				logger.debug("got AUTH challenge, sending response")
				echallenge = data
				self.sendLine("AUTH:"+self.factory.answerChallenge(echallenge))
				return
			elif command == "AUTH" and status == ':':
				# response accepted, authenticated
				logger.debug("AUTH challenge accepted, success")
				self.auth = True
				self.factory.clientReady(self)
				#print "authenticated"
			else:
				if command == "AUTH" and status == "!":
					logger.warn("authentication failed (is FLUDHOME set"
						" correctly?)")
					print "authentication failed (is FLUDHOME set correctly?)"
				else:
					logger.warn("unknown message received before being"
							" authenticated:")
					logger.warn("  %s : %s" % (command, status))
					print "unknown message received before being authenticated:"
					print "  %s : %s" % (command, status)
				self.factory.setDie()
		elif command == "DIAG":
			subcommand = data[:4]
			data = data[4:]
			if subcommand == "NODE":
				logger.debug("DIAG NODE: %s" % data)
				data = fdecode(data)
				result = ""
				for i in data:
					score = i[4]
					petID = "%064x" % i[2]
					netID = "%s:%d" % (i[0], i[1])
					petID = petID[:(70-len(netID))]+"..."
					result += "%d %s %s\n" % (score, netID, petID)
				result += "%d known nodes\n" % len(data)
				d = self.factory.pending['NODE'].pop('')
				d.callback(result)
				return
			if subcommand == "BKTS":
				logger.debug("DIAG BKTS")
				data = fdecode(data)
				result = ""
				for i in data:
					for bucket in i:
						result += "Bucket %s:\n" % bucket
						for k in i[bucket]:
							id = "%064x" % k[2]
							netID = "%s:%d" % (k[0], k[1])
							result += "  %s %s...\n" \
									% (netID,id[:72-len(netID)])
				d = self.factory.pending['BKTS'].pop('')
				d.callback(result)
				return
			elif status == ':':
				response, data = data.split(status, 1)
				logger.debug("DIAG %s: success" % subcommand)
				d = self.factory.pending[subcommand].pop(data)
				d.callback(fdecode(response))
			elif status == "!":
				response, data = data.split(status, 1)
				logger.debug("DIAG %s: failure" % subcommand)
				d = self.factory.pending[subcommand].pop(data)
				d.errback(failure.DefaultException(response))
		elif status == ':':
			response, data = data.split(status, 1)
			logger.debug("%s: success" % command)
			d = self.factory.pending[command].pop(data)
			d.callback(fdecode(response))
		elif status == "!":
			response, data = data.split(status, 1)
			logger.debug("%s: failure" % command)
			if self.factory.pending.has_key(command):
				if not self.factory.pending[command].has_key(data):
					print "data key is '%s'" % data
					print "pending is '%s'" % self.factory.pending[command]
					if len(self.factory.pending[command]):
						d = self.factory.pending[command].popitem()
						d.errback(failure.DefaultException(response))
				else:
					d = self.factory.pending[command].pop(data)
					d.errback(failure.DefaultException(response))
			else:
				print "failed command '%s' not in pending?" % command
				print "pending is: %s" % self.factory.pending
		if command != 'AUTH' and command != 'DIAG' and \
				not None in self.factory.pending[command].values():
			logger.debug("%s done at %s" % (command, time.ctime()))


class LocalClientFactory(ClientFactory):
	protocol = LocalClient

	def __init__(self, config):
		self.config = config
		self.messageQueue = []
		self.client = None
		self.die = False
		self.pending = {'PUTF': {}, 'CRED': {}, 'GETI': {}, 'GETF': {}, 
				'FNDN': {}, 'STOR': {}, 'RTRV': {}, 'VRFY': {}, 'FNDV': {}, 
				'CRED': {}, 'LIST': {}, 'GETM': {}, 'PUTM': {}, 'NODE': {}, 
				'BKTS': {}}

	def clientConnectionFailed(self, connector, reason):
		#print "connection failed: %s" % reason
		logger.warn("connection failed: %s" % reason)
		self.cleanup("connection failed: %s" % reason)

	def clientConnectionLost(self, connector, reason):
		#print "connection lost: %s" % reason
		logger.debug("connection lost: %s" % reason)
		self.cleanup("connection lost: %s" % reason)

	def cleanup(self, msg):
		# override me for cleanup
		print msg;

	def clientReady(self, instance):
		self.client = instance
		logger.debug("client ready, sending [any] queued msgs")
		for i in self.messageQueue:
			self._sendMessage(i)

	def _sendMessage(self, msg):
		if self.client:
			logger.debug("sending msg '%s'" % msg)
			self.client.sendLine(msg)
		else:
			logger.debug("queueing msg '%s'" % msg)
			self.messageQueue.append(msg)
	
	def answerChallenge(self, echallenge):
		logger.debug("answering challenge")
		echallenge = (fdecode(echallenge),)
		challenge = self.config.Kr.decrypt(echallenge)
		return challenge

	def expire(self, pending, key):
		if pending.has_key(fname):
			logger.debug("timing out operation for %s" % key)
			#print "timing out operation for %s" % key
			pending.pop(key)
	
	def addFile(self, type, fname):
		logger.debug("addFile %s %s" % (type, fname))
		if not self.pending[type].has_key(fname):
			d = defer.Deferred()
			self.pending[type][fname] = d
			self._sendMessage(type+"?"+fname)
			return d
		else:
			return self.pending[type][fname]
			
	def sendPING(self, host, port):
		logger.debug("sendPING")
		d = defer.Deferred()
		d.errback(failure.DefaultException(
			"ping not yet implemented in FludLocalClient"))
		return d

	def sendPUTF(self, fname):
		logger.debug("sendPUTF %s" % fname)
		if os.path.isdir(fname):
			dirlist = os.listdir(fname)
			dlist = []
			for i in dirlist:
				dlist.append(self.sendPUTF(os.path.join(fname,i)))
			dl = defer.DeferredList(dlist)
			return dl
		elif not self.pending['PUTF'].has_key(fname):
			d = defer.Deferred()
			self.pending['PUTF'][fname] = d
			self._sendMessage("PUTF?"+fname)
			#reactor.callLater(opTimeout, self.expire, self.pendingPUTF, fname)
			return d
		else:
			return self.pending['PUTF'][fname]
	
	def sendCRED(self, passphrase, email):
		logger.debug("sendCRED")
		key = fencode((self.config.Ku.encrypt(passphrase)[0], email))
		if not self.pending['CRED'].has_key(key):
			d = defer.Deferred()
			self.pending['CRED'][key] = d
			self._sendMessage("CRED?"+key)
			return d
		else:
			return self.pending['CRED'][key]
	
	def sendGETI(self, fID):
		logger.debug("sendGETI")
		if not self.pending['GETI'].has_key(fID):
			d = defer.Deferred()
			self.pending['GETI'][fID] = d
			self._sendMessage("GETI?"+fID)
			return d
		else:
			return self.pending['GETI'][fID]

	def sendGETF(self, fname):
		logger.debug("sendGETF")
		master = listMeta(self.config)
		if master.has_key(fname):
			return self.addFile("GETF",fname)
		elif fname[-1:] == os.path.sep:
			dlist = []
			for name in master:
				if fname == name[:len(fname)]:
					dlist.append(self.addFile("GETF",name))
			dl = defer.DeferredList(dlist)
			return dl

	def sendFNDN(self, nID):
		logger.debug("sendFNDN")
		if not self.pending['FNDN'].has_key(nID):
			d = defer.Deferred()
			self.pending['FNDN'][nID] = d
			self._sendMessage("FNDN?"+nID)
			return d
		else:
			return self.pending['FNDN'][nID]

	def sendLIST(self):
		logger.debug("sendLIST")
		if not self.pending['LIST'].has_key(""):
			d = defer.Deferred()
			self.pending['LIST'][''] = d
			logger.debug("LIST['']=%s" % d)
			self._sendMessage("LIST?")
			return d
		else:
			return self.pending['LIST']['']
	
	def sendGETM(self):
		logger.debug("sendGETM")
		if not self.pending['GETM'].has_key(''):
			d = defer.Deferred()
			self.pending['GETM'][''] = d
			logger.debug("GETM['']=%s" % d)
			self._sendMessage("GETM?")
			return d
		else:
			return self.pending['GETM']['']

	def sendPUTM(self):
		logger.debug("sendPUTM")
		if not self.pending['PUTM'].has_key(''):
			d = defer.Deferred()
			self.pending['PUTM'][''] = d
			self._sendMessage("PUTM?")
			return d
		else:
			return self.pending['PUTM']['']

	def sendDIAGNODE(self):
		logger.debug("sendDIAGNODE")
		if not self.pending['NODE'].has_key(''):
			d = defer.Deferred()
			self.pending['NODE'][''] = d
			self._sendMessage("DIAG?NODE")
			return d
		else:
			return self.pending['NODE']['']

	def sendDIAGBKTS(self):
		logger.debug("sendDIAGBKTS")
		if not self.pending['BKTS'].has_key(''):
			d = defer.Deferred()
			self.pending['BKTS'][''] = d
			self._sendMessage("DIAG?BKTS")
			return d
		else:
			return self.pending['BKTS']['']

	def sendDIAGSTOR(self, command):
		logger.debug("sendDIAGSTOR")
		if not self.pending['STOR'].has_key(command):
			d = defer.Deferred()
			self.pending['STOR'][command] = d
			self._sendMessage("DIAG?STOR "+command)
			return d
		else:
			return self.pending['STOR'][command]

	def sendDIAGRTRV(self, command):
		logger.debug("sendDIAGRTRV")
		if not self.pending['RTRV'].has_key(command):
			d = defer.Deferred()
			self.pending['RTRV'][command] = d
			self._sendMessage("DIAG?RTRV "+command)
			return d
		else:
			return self.pending['RTRV'][command]

	def sendDIAGVRFY(self, command):
		logger.debug("sendDIAGVRFY")
		if not self.pending['VRFY'].has_key(command):
			d = defer.Deferred()
			self.pending['VRFY'][command] = d
			self._sendMessage("DIAG?VRFY "+command)
			return d
		else:
			return self.pending['VRFY'][command]

	def sendDIAGFNDV(self, val):
		logger.debug("sendDIAGFNDV")
		if not self.pending['FNDV'].has_key(val):
			d = defer.Deferred()
			self.pending['FNDV'][val] = d
			self._sendMessage("FNDV?"+val)
			return d
		else:
			return self.pending['FNDV'][val]

	def setDie(self):
		self.die = True

# XXX: this should move into FludNode side of things (LocalClientPrimitives).
# anything that calls this should make calls ('LIST', others as necessary) to
# get at master metadata, otherwise we could have multiple writer problems.
# FludNode should make the file ro while running, too.
# And everyone that does anything with the master metadata should do it through
# methods of FludConfig, instead of by direct access to the file.
def listMeta(config):
	fmaster = open(os.path.join(config.metadir,config.metamaster), 'r')
	master = fmaster.read()
	fmaster.close()
	if master == "":
		master = {}
	else:
		master = fdecode(master)
	return master

