#!/usr/bin/python

import sys, os, time, stat
from twisted.internet import reactor

from FludConfig import FludConfig
from fencode import *
from FludCrypto import *

from Protocol.LocalClient import *

CHECKTIME=30

class FludScheduler:

	def __init__(self, config, factory):
		self.config = config
		self.factory = factory
		self.fileconfig = None
		self.fileconfigMTime = 0

	def checkConfig(self):
		# check config file to see if it has changed, then reparse it
		if not self.fileconfig:
			# first time through
			print "checking fileconfig (initial)"
			if os.environ.has_key('FLUDHOME'):
				fludhome = os.environ['FLUDHOME']
			else:
				fludhome = os.environ['HOME']+"/.flud"
			# XXX: fludfile.conf should be in config
			self.fileconfig = os.path.join(fludhome, "fludfile.conf")
			if os.path.isfile(self.fileconfig):
				print "reading fileconfig"
				file = open(self.fileconfig, 'r')
				self.files = eval(file.read())
				file.close()
				self.fileconfigMTime = os.stat(self.fileconfig)[stat.ST_MTIME]
				return True
			else:
				print "no fileconfig to read"
		elif os.path.isfile(self.fileconfig):
			mtime = os.stat(self.fileconfig)[stat.ST_MTIME]
			if mtime > self.fileconfigMTime:
				print "fileconfig changed"
				self.fileconfigMTime = mtime
				file = open(self.fileconfig, 'r')
				self.files = eval(file.read())
				file.close()
				return True
		return False

	def checkFilesystem(self):
		# check fs to see if any of the files we are backing up have changed
		pass

	def run(self):
		print "run"
		if self.checkConfig():
			print "time to backup!"
		reactor.callLater(CHECKTIME, self.run)

def main():
	config = FludConfig()
	config.load(doLogging=False)

	factory = LocalClientFactory(config)
	
	if len(sys.argv) == 2:
		config.clientport = int(sys.argv[1])
	print "connecting to localhost:%d" % config.clientport
	reactor.connectTCP('localhost', config.clientport, factory)

	scheduler = FludScheduler(config, factory)

	# XXX: instead of callInThread, schedule a timer via reactor
	#reactor.callInThread(scheduler.run)
	reactor.callLater(1, scheduler.run)

	#print reactor.threadpool.threads
	reactor.run()


if __name__ == '__main__':
	main()
