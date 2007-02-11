#!/usr/bin/python

import sys, os, time
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.python import threadable
threadable.init()

from FludConfig import FludConfig
from fencode import *
from FludCrypto import *

from Protocol.LocalPrimitives import LocalProtocol

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
		for i in reactor.threadpool.threads:
			i._Thread__stop()
		reactor.stop()

	def clientConnectionLost(self, connector, reason):
		#print "connection lost: %s" % reason
		print
		for i in reactor.threadpool.threads:
			i._Thread__stop() # XXX: hack, but all we've got againts raw_input
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


def promptUser(factory):
	done = False
	helpDict = {}
	while not done and not factory.die:
		time.sleep(0.15)
		for c in factory.pending:
			for i in factory.pending[c].keys():
				if factory.pending[c][i] == True:
					print "%s on %s completed successfully" % (c, i)
					factory.pending[c].pop(i)
				elif factory.pending[c][i] == False:
					print "%s on %s failed" % (c, i)
					factory.pending[c].pop(i)
				else:
					print "%s on %s pending" % (c, i)
		command = raw_input("%s> " % time.ctime())
		commands = command.split(' ') # XXX: should tokenize on any whitespace
		commandkey = commands[0][:4]
		
		# core client operations
		helpDict['exit'] = "exit from the client"
		helpDict['help'] = "display this help message"
		helpDict['ping'] = "send a GETID() message: 'ping host port'"
		helpDict['putf'] = "store a file: 'putf canonicalfilepath'"
		helpDict['getf'] = "retrieve a file: 'getf canonicalfilepath'"
		helpDict['geti'] = "retrieve a file by CAS key: 'geti fencodedCASkey'"
		helpDict['fndn'] = "send a FINDNODE() message: 'fndn hexIDstring'"
		helpDict['list'] = "list stored files (read from local metadata)"
		helpDict['putm'] = "store master metadata"
		helpDict['getm'] = "retrieve master metadata"
		helpDict['cred'] = "send encrypted private credentials: cred"\
				" passphrase emailaddress"
		helpDict['node'] = "list known nodes"
		helpDict['buck'] = "print k buckets"
		helpDict['stat'] = "show pending actions"
		helpDict['stor'] = "store a block to a given node:"\
				" 'stor host:port,fname'"
		helpDict['rtrv'] = "retrieve a block from a given node:"\
				" 'rtrv host:port,fname'"
		helpDict['vrfy'] = "verify a block on a given node:"\
				" 'vrfy host:port:offset-length,fname'"
		helpDict['fndv'] = "retrieve a value from the DHT: 'fndv hexkey'"
		if commandkey == 'exit' or commandkey == 'quit':
			done = True
		elif commandkey == 'help':
			printHelp(helpDict)
		elif commandkey == 'ping':
			# ping a host
			# format: 'ping host port'
			reactor.callFromThread(factory.sendPING, commands[1], commands[2])
		elif commandkey == 'putf':
			# store a file
			# format: 'putf canonicalfilepath'
			reactor.callFromThread(factory.sendPUTF, commands[1])
		elif commandkey == 'getf':
			# retrieve a file
			# format: 'getf canonicalfilepath'
			reactor.callFromThread(factory.sendGETF, commands[1])
		elif commandkey == 'geti':
			# retrieve a file by CAS ID
			# format: 'geti fencoded_CAS_ID'
			reactor.callFromThread(factory.sendGETI, commands[1])
		elif commandkey == 'fndn':
			# find a node (or the k-closest nodes)
			# format: 'fndn hexIDstring'
			reactor.callFromThread(factory.sendFNDN, commands[1])
		elif commandkey == 'list':
			# list stored files
			master = listMeta(factory.config)
			for i in master:
				if not isinstance(master[i],dict):
					print "%s: %s" % (i, fencode(master[i]))
		elif commandkey == 'putm':
			# store master metadata
			reactor.callFromThread(factory.sendPUTM)
		elif commandkey == 'getm':
			# retrieve master metadata
			reactor.callFromThread(factory.sendGETM)
		elif commandkey == 'cred':
			# send encrypted private credentials to an email address
			# format: 'cred passphrase emailaddress'
			# XXX: add optional passphrase hint after emailaddress
			reactor.callFromThread(factory.sendCRED, 
					command[len(commands[0])+1:-len(commands[-1])-1], 
					commands[-1])
			
		# the following are diagnostic operations, debug-only utility
		elif commandkey == 'node':
			# list known nodes
			reactor.callFromThread(factory.sendDIAGNODE)
		elif commandkey == 'buck':
			# show k-buckets
			reactor.callFromThread(factory.sendDIAGBKTS)
		elif commandkey == 'stat':
			# show pending actions
			print factory.pending
		elif commandkey == 'stor':
			# stor a block to a given node.  format: 'stor host:port,fname'
			storcommands = commands[1].split(',')
			try:
				fileid = int(storcommands[1], 16)
			except:
				linkfile = fencode(long(hashfile(storcommands[1]),16))
				if (os.path.islink(linkfile)):
					os.remove(linkfile)
				os.symlink(storcommands[1], linkfile)
				storcommands[1] = linkfile
				# XXX: delete this when the command finishes
			commands[1] = "%s,%s" % (storcommands[0], storcommands[1])
			reactor.callFromThread(factory.sendDIAGSTOR, 'STOR '+commands[1])
		elif commandkey == 'rtrv':
			# retrive a block from a given node. format: 'rtrv host:port,fname'
			reactor.callFromThread(factory.sendDIAGRTRV, 'RTRV '+commands[1])
		elif commandkey == 'vrfy':
			# verify a block on a given node.
			# format: 'vrfy host:port:offset-length,fname'
			reactor.callFromThread(factory.sendDIAGVRFY, 'VRFY '+commands[1])
		elif commandkey == 'fndv':
			# try to retrieve a value from the DHT
			# format: 'fndv key'
			reactor.callFromThread(factory.sendDIAGFNDV, commands[1])

	reactor.callFromThread(reactor.stop)


def main():
	config = FludConfig()
	config.load(doLogging=False)
	factory = LocalClientFactory(config)
	if len(sys.argv) == 2:
		config.clientport = int(sys.argv[1])
	print "connecting to localhost:%d" % config.clientport
	reactor.connectTCP('localhost', config.clientport, factory)
	reactor.callInThread(promptUser, factory)
	print reactor.threadpool.threads
	reactor.run()


if __name__ == '__main__':
	main()
