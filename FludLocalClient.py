#!/usr/bin/python

"""
FludLocalClient.py, (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 2.

FludLocalClient provides a command-line client for interacting with FludNode.
"""

import sys, os, time
from twisted.internet import reactor

from FludConfig import FludConfig
from fencode import *
from FludCrypto import *

from Protocol.LocalClient import *

logger = logging.getLogger('flud')

class CmdClientFactory(LocalClientFactory):

	def __init__(self, config):
		LocalClientFactory.__init__(self, config)
		self.quit = False
		self.msgs = []

	def callFactory(self, func, commands, msgs):
		# since we can't call factory methods from the promptUser thread, we
		# use this as a convenience to put those calls back in the event loop
		reactor.callFromThread(self.doFactoryMethod, func, commands, msgs)

	def doFactoryMethod(self, func, commands, msgs):
		d = func()
		d.addCallback(self.queueResult, msgs, '%s succeeded' % commands)
		d.addErrback(self.queueError, msgs, '%s failed' % commands)
		return d

	def promptUser(self):
		helpDict = {}

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
		helpDict['dlet'] = "delete from the stor: '[XXX]'"
		if commandkey == 'exit' or commandkey == 'quit':
			self.quit = True
		elif commandkey == 'help':
			self.printHelp(helpDict)
		elif commandkey == 'ping':
			# ping a host
			# format: 'ping host port'
			func = lambda: self.sendPING(commands[1], commands[2])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'putf':
			# store a file
			# format: 'putf canonicalfilepath'
			func = lambda: self.sendPUTF(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'getf':
			# retrieve a file
			# format: 'getf canonicalfilepath'
			func = lambda: self.sendGETF(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'geti':
			# retrieve a file by CAS ID
			# format: 'geti fencoded_CAS_ID'
			func = lambda: self.sendGETI(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'fndn':
			# find a node (or the k-closest nodes)
			# format: 'fndn hexIDstring'
			func = lambda: self.sendFNDN(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'list':
			# list stored files
			master = listMeta(self.config)
			for i in master:
				if not isinstance(master[i], dict):
					print "%s: %s" % (i, fencode(master[i]))
		elif commandkey == 'putm':
			# store master metadata
			self.callFactory(self.sendPUTM, commands, self.msgs)
		elif commandkey == 'getm':
			# retrieve master metadata
			self.callFactory(self.sendGETM, commands, self.msgs)
		elif commandkey == 'cred':
			# send encrypted private credentials to an email address
			# format: 'cred passphrase emailaddress'
			func = lambda: self.sendCRED(
					command[len(commands[0])+1:-len(commands[-1])-1], 
					commands[-1])
			self.callFactory(func, commands, self.msgs)
			
		# the following are diagnostic operations, debug-only utility
		elif commandkey == 'node':
			# list known nodes
			self.callFactory(self.sendDIAGNODE, commands, self.msgs)
		elif commandkey == 'buck':
			# show k-buckets
			self.callFactory(self.sendDIAGBKTS, commands, self.msgs)
		elif commandkey == 'stat':
			# show pending actions
			print self.pending
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
				# XXX: delete this file when the command finishes
			commands[1] = "%s,%s" % (storcommands[0], storcommands[1])
			func = lambda: self.sendDIAGSTOR(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'rtrv':
			# retrive a block from a given node. format: 'rtrv host:port,fname'
			func = lambda: self.sendDIAGRTRV(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'vrfy':
			# verify a block on a given node.
			# format: 'vrfy host:port:offset-length,fname'
			logger.debug("vrfy(%s)" % commands[1])
			func = lambda: self.sendDIAGVRFY(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif commandkey == 'dlet':
			print "not yet implemented"
		elif commandkey == 'fndv':
			# try to retrieve a value from the DHT
			# format: 'fndv key'
			func = lambda: self.sendDIAGFNDV(commands[1])
			self.callFactory(func, commands, self.msgs)
		elif command != "":
			reactor.callFromThread(self.queueError, None, self.msgs, 
					"illegal command '%s'" % command)


	def queueResult(self, r, l, msg):
		logger.debug("got result %s" % msg)
		l.append((r, msg))

	def queueError(self, r, l, msg):
		logger.debug("got error %s" % msg)
		if r:
			l.append((r.getErrorMessage(), msg))
		else:
			l.append((None, msg))

	def printHelp(self, helpDict):
		helpkeys = helpDict.keys()
		helpkeys.sort()
		for i in helpkeys:
			print "%s:\t %s" % (i, helpDict[i])

	def promptLoop(self, r):
		for c in self.pending:
			for i in self.pending[c].keys():
				if self.pending[c][i] == True:
					print "%s on %s completed successfully" % (c, i)
					self.pending[c].pop(i)
				elif self.pending[c][i] == False:
					print "%s on %s failed" % (c, i)
					self.pending[c].pop(i)
				else:
					print "%s on %s pending" % (c, i)

		while len(self.msgs) > 0:
			# this prints in reverse order, perhaps pop() all into a new list,
			# reverse, then print
			(errmsg, m) = self.msgs.pop()
			if errmsg:
				print "<- %s:\n%s" % (m, errmsg) 
			else:
				print "<- %s" % m

		if self.quit:
			reactor.stop()
		else:
			d = threads.deferToThread(self.promptUser)
			d.addCallback(self.promptLoopDelayed)
			d.addErrback(self.err)

	def promptLoopDelayed(self, r):
		# give the reactor loop time to fire any quick cbs/ebs
		reactor.callLater(0.1, self.promptLoop, r)

	def clientConnectionLost(self, connector, reason):
		if not self.quit:
			LocalClientFactory.clientConnectionLost(connector, reason)

	def cleanup(self, msg):
		self.quit = True
		self.err(msg)

	def err(self, r):
		print "bah!: %s" % r
		reactor.stop()

def main():
	config = FludConfig()
	config.load(doLogging=False)

	logger.setLevel(logging.DEBUG)
	handler = logging.FileHandler('/tmp/fludclient.log')
	formatter = logging.Formatter('%(asctime)s %(filename)s:%(lineno)d'
			' %(name)s %(levelname)s: %(message)s', datefmt='%H:%M:%S')
	handler.setFormatter(formatter)
	logger.addHandler(handler)

	factory = CmdClientFactory(config)
	
	if len(sys.argv) == 2:
		config.clientport = int(sys.argv[1])
	
	print "connecting to localhost:%d" % config.clientport
	
	reactor.connectTCP('localhost', config.clientport, factory)
	
	factory.promptLoop(None)
	
	reactor.run()


if __name__ == '__main__':
	main()
