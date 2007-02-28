#!/usr/bin/python

import sys, os, time, stat
from twisted.internet import reactor

from FludConfig import FludConfig
from fencode import *
from FludCrypto import *

from Protocol.LocalClient import *
from FludClient import CheckboxState  # XXX: CheckboxState belongs elsewhere?

CHECKTIME=5

class FludScheduler:

	def __init__(self, config, factory):
		self.config = config
		self.factory = factory
		self.configfile = None
		self.configfileMTime = 0
		self.fileChangeTime = 0

	def readConfig(self, mtime=None):
		print "reading configfile"
		file = open(self.configfile, 'r')
		self.fileconfig = eval(file.read())
		file.close()
		if mtime:
			self.configfileMTime = mtime
		else:
			self.configfileMTime = os.stat(self.configfile)[stat.ST_MTIME]

		self.fileconfigSelected = set([f for f in self.fileconfig 
				if self.fileconfig[f] == CheckboxState.SELECTED 
				or self.fileconfig[f] == CheckboxState.SELECTEDCHILD])
		self.fileconfigExcluded = set([f for f in self.fileconfig 
				if self.fileconfig[f] == CheckboxState.EXCLUDED 
				or self.fileconfig[f] == CheckboxState.EXCLUDEDCHILD])

	# The file[s]ChangeStat are the worst possible way to detect file changes.
	# Much more efficient to use inotify/dnotify/fam/gamin/etc., as well as
	# more correct (no way to detect cp -a or -p, for example, with stat).
	# But, these are a fallback method when those aren't present, and are fine
	# for testing.
	def fileChangedStat(self, file, fileChangeTime=None):
		if os.path.isfile(file) or os.path.isdir(file):
			mtime = os.stat(file)[stat.ST_MTIME]
			if not fileChangeTime:
				fileChangeTime = self.fileChangeTime
			if mtime > fileChangeTime:
				return True
		return False

	def filesChangedStat(self, files, fileChangeTime=None):
		result = []
		for f in files:
			if self.fileChangedStat(f, fileChangeTime):
				result.append(f)
		return result

	# Change these to point to something other than the xxxStat() methods
	def fileChanged(self, file, fileChangeTime=None):
		"""
		>>> now = time.time()
		>>> f1 = tmpfile.mktemp()
		>>> 
		"""
		return self.fileChangedStat(file, fileChangeTime)

	def filesChanged(self, files, fileChangeTime=None):
		return self.filesChangedStat(files, fileChangeTime)

	def checkConfig(self):
		# check config file to see if it has changed, then reparse it
		if not self.configfile:
			# first time through
			print "checking configfile (initial)"
			if os.environ.has_key('FLUDHOME'):
				fludhome = os.environ['FLUDHOME']
			else:
				fludhome = os.environ['HOME']+"/.flud"
			# XXX: fludfile.conf should be in config
			self.configfile = os.path.join(fludhome, "fludfile.conf")
			if os.path.isfile(self.configfile):
				self.readConfig()
				return True
			else:
				print "no configfile to read"
		elif os.path.isfile(self.configfile):
			if self.fileChanged(self.configfile, self.configfileMTime):
				print "configfile changed"
				self.readConfig(mtime)
				return True
		return False

	def checkFilesystem(self):
		checkedFiles = set()
		changedFiles = set()

		def checkList(list):
			#print "checkList: %s" % list
			#print "checkedFiles: %s" % checkedFiles
			for entry in list:
				# XXX: if entry is in manifest, and its mtime is not earlier
				# than the time used by fileChanged, skip it (add 'and' clause)
				if entry not in checkedFiles and \
						entry not in self.fileconfigExcluded:
					if os.path.isdir(entry):
						#print "dir %s" % entry
						dirfiles = [os.path.join(entry, i) 
								for i in os.listdir(entry)]
						checkedFiles.update([entry,])
						checkList(dirfiles)
					elif self.fileChanged(entry):
						if os.path.isfile(entry):
							changedFiles.update([entry,])
							#print "file %s changed" % entry
						else:
							print "entry ?? %s ?? changed" % entry
					checkedFiles.update([entry,])

		checkList(self.fileconfigSelected)
		self.fileChangeTime = time.time()
		return changedFiles

	def run(self):
		print "run"
		self.checkConfig()
		changedFiles = self.checkFilesystem()
		print "%s changed" % changedFiles
		# XXX: store files listed in changedFiles before scheduling run again
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

	reactor.callLater(1, scheduler.run)

	reactor.run()

if __name__ == '__main__':
	main()
