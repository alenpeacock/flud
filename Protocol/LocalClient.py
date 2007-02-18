#!/usr/bin/python
"""
LocalClient.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 2.

LocalClient provides client functions which can be called to send commands to
a local FludNode instance.
"""

import sys, os, time
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.python import threadable
threadable.init()

from fencode import *

from LocalPrimitives import *

opTimeout = 1200
VALIDOPS = LocalProtocol.commands.keys() + ['AUTH', 'DIAG']

class LocalClient(LineReceiver):
	MAX_LENGTH = 300000
	auth=False
	
	def connectionMade(self):
		self.auth=False
		self.sendLine("AUTH?")

	def lineReceived(self, line):
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
				echallenge = data
				self.sendLine("AUTH:"+self.factory.answerChallenge(echallenge))
				return
			elif command == "AUTH" and status == ':':
				# response accepted, authenticated
				self.auth = True
				self.factory.clientReady(self)
				#print "authenticated"
			else:
				if command == "AUTH" and status == "!":
					print "authentication failed (is FLUDHOME set correctly?)"
				else:
					print "unknown message received before being authenticated:"
					print "  %s : %s" % (command, status)
				self.factory.setDie()
		elif command == "DIAG":
			if data[:4] == "NODE":
				data = eval(data[4:])
				for i in data:
					petID = "%064x" % i[2]
					petID = petID[:24]+"..."
					print "%s:%d %s" % (i[0], i[1], petID)
				print "%d known nodes" % len(data)
				return
			if data[:4] == "BKTS":
				data = eval(data[4:])
				print "-------------------------"
				for i in data:
					for bucket in i:
						print "Bucket %s:" % bucket
						for k in i[bucket]:
							id = "%064x" % k[2]
							print "  %s:%d %s..." % (k[0],k[1],id[:12])
				return
			elif status == ':':
				self.factory.pending[data[:4]][data] = True
			elif status == "!":
				self.factory.pending[data[:4]][data] = False
		elif status == ':':
			self.factory.pending[command][data] = True
		elif status == "!":
			self.factory.pending[command][data] = False
		if command != 'AUTH' and command != 'DIAG' and \
				not None in self.factory.pending[command].values():
			print "%s done at %s" % (command, time.ctime())


class LocalClientFactory(ClientFactory):
	protocol = LocalClient

	def __init__(self, config):
		self.config = config
		self.messageQueue = []
		self.client = None
		self.die = False
		self.pending = {'PUTF': {}, 'GETF': {}, 'FNDN': {}, 
			'STOR': {}, 'RTRV': {}, 'VRFY': {}, 'FNDV': {}, 
			'CRED': {}, 'GETM': {}, 'PUTM': {} }

	def clientConnectionFailed(self, connector, reason):
		print "connection failed: %s" % reason
		print
		if reactor.threadpool:
			for i in reactor.threadpool.threads:
				i._Thread__stop()
		reactor.stop()

	def clientConnectionLost(self, connector, reason):
		#print "connection lost: %s" % reason
		print
		if reactor.threadpool:
			for i in reactor.threadpool.threads:
				# XXX: hack, but all we've got against raw_input
				i._Thread__stop() 
		reactor.stop()

	def clientReady(self, instance):
		self.client = instance
		for i in self.messageQueue:
			self._sendMessage(i)

	def _sendMessage(self, msg):
		if self.client:
			self.client.sendLine(msg)
		else:
			self.messageQueue.append(msg)
	
	def answerChallenge(self, echallenge):
		echallenge = (fdecode(echallenge),)
		challenge = self.config.Kr.decrypt(echallenge)
		return challenge

	def expire(self, pending, key):
		if pending.has_key(fname):
			print "timing out operation for %s" % key
			pending.pop(key)
	
	def addFile(self, type, fname):
		if not self.pending[type].has_key(fname):
			self.pending[type][fname] = None
			self._sendMessage(type+"?"+fname)

	def sendPING(self, host, port):
		print "ping not yet implemented in FludLocalClient"
		pass

	def sendPUTF(self, fname):
		if os.path.isdir(fname):
			dirlist = os.listdir(fname)
			for i in dirlist:
				self.sendPUTF(os.path.join(fname,i))
		elif not self.pending['PUTF'].has_key(fname):
			self.pending['PUTF'][fname] = None
			self._sendMessage("PUTF?"+fname)
			#reactor.callLater(opTimeout, self.expire, self.pendingPUTF, fname)
	
	def sendCRED(self, passphrase, email):
		self._sendMessage("CRED?"
				+fencode((self.config.Ku.encrypt(passphrase)[0], email)))
	
	def sendGETI(self, fID):
		if not self.pendingi['GETI'].has_key(fID):
			self.pending['GETI'][fID] = None
			self._sendMessage("GETI?"+fID)

	def sendGETF(self, fname):
		master = listMeta(self.config)
		if master.has_key(fname):
			self.addFile("GETF",fname)
		elif fname[-1:] == os.path.sep:
			for name in master:
				if fname == name[:len(fname)]:
					self.addFile("GETF",name)

	def sendFNDN(self, nID):
		if not self.pending['FNDN'].has_key(nID):
			self.pending['FNDN'][nID] = None
			self._sendMessage("FNDN?"+nID)
	
	def sendGETM(self):
		self._sendMessage("GETM?")

	def sendPUTM(self):
		self._sendMessage("PUTM?")

	def sendDIAGNODE(self):
		self._sendMessage("DIAG?NODE")

	def sendDIAGBKTS(self):
		self._sendMessage("DIAG?BKTS")

	def sendDIAGSTOR(self, command):
		self.pending['STOR'][command] = None
		self._sendMessage("DIAG?"+command)

	def sendDIAGRTRV(self, command):
		self.pending['RTRV'][command] = None
		print "DRTRV pending '%s'" % command
		self._sendMessage("DIAG?"+command)

	def sendDIAGVRFY(self, command):
		self.pending['VRFY'][command] = None
		self._sendMessage("DIAG?"+command)

	def sendDIAGFNDV(self, val):
		if not self.pending['FNDV'].has_key(val):
			self.pending['FNDV'][val] = None
			self._sendMessage("FNDV?"+val)

	def setDie(self):
		self.die = True

def listMeta(config):
	fmaster = open(config.metadir+"/"+config.metamaster, 'r')
	master = fmaster.read()
	fmaster.close()
	if master == "":
		master = {}
	else:
		master = fdecode(master)
	return master

def printHelp(helpDict):
	for i in helpDict:
		print "%s:\t %s" % (i, helpDict[i])

