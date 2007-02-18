#!/usr/bin/python

import sys, os, time, stat
from twisted.internet import reactor

from FludConfig import FludConfig
from fencode import *
from FludCrypto import *

from Protocol.LocalClient import *

CHECKTIME=5

# XXX: remove.  this is in FludClient.py (need to extract commonality)
class CheckboxState:
	(UNSELECTED, SELECTED, SELECTEDCHILD, SELECTEDPARENT, EXCLUDED,
			EXCLUDEDCHILD) = range(6)
		    
	def offset(oldstate, newstate):
		return newstate - oldstate
	offset = staticmethod(offset)


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
	# more correct (no way to detect cp -A, for example, with stat).  But,
	# these are a fallback, method when those aren't present, and are fine for
	# testing.
	def fileChangedStat(self, file, fileChangeTime=None):
		#print "checking %s" % file
		if os.path.isfile(file) or os.path.isdir(file):
			mtime = os.stat(file)[stat.ST_MTIME]
			if not fileChangeTime:
				fileChangeTime = self.fileChangeTime
			if mtime > fileChangeTime:
				#print "CHANGED"
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
		return self.fileChangedStat(file, fileChangeTime)

	def filesChanged(self, file, fileChangeTime=None):
		return self.filesChangedStat(file, fileChangeTime)

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
		self.toCheck = set()
		self.checkedFiles = set()
		self.changedFiles = set()

		def checkList(list):
			#print "checkList: %s" % list
			#print "checkedFiles: %s" % self.checkedFiles
			for entry in list:
				if entry not in self.checkedFiles and \
						entry not in self.fileconfigExcluded:
					if os.path.isdir(entry):
						print "dir %s" % entry
						dirfiles = [os.path.join(entry, i) 
								for i in os.listdir(entry)]
						self.checkedFiles.update([entry,])
						checkList(dirfiles)
					elif self.fileChanged(entry):
						if os.path.isfile(entry):
							print "file %s changed" % entry
						else:
							print "entry ?? %s ?? changed" % entry
					self.changedFiles.update([entry,])
					self.checkedFiles.update([entry,])

		checkList(self.fileconfigSelected)
		self.fileChangeTime = time.time()

	def run(self):
		print "run"
		self.checkConfig()
		self.checkFilesystem()
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
