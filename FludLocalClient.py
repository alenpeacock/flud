"""
FludLocalClient.py, (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 2.

FludLocalClient provides a command-line client for interacting with FludNode.
"""
#!/usr/bin/python

import sys, os, time
from twisted.internet import reactor

from FludConfig import FludConfig
from fencode import *
from FludCrypto import *

from Protocol.LocalClient import *

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
				if not isinstance(master[i], dict):
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
