#!/usr/bin/python

"""
FludScheduler.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), verison 3.

FludScheduler is the process monitors files for changes, and then tells flud to
back them up.
"""

import sys, os, time, stat
from twisted.internet import reactor

from flud.FludConfig import FludConfig

from flud.protocol.LocalClient import *
from flud.CheckboxState import CheckboxState

CHECKTIME=5

class FludScheduler:

	def __init__(self, config, factory):
		self.config = config
		self.factory = factory
		
		self.fileconfigfile = None
		self.fileconfigfileMTime = 0
		self.fileChangeTime = 0

		self.fileconfigSelected = set()
		self.fileconfigExcluded = set()
		
		self.getMasterMetadata()

	def getMasterMetadata(self):
		d = self.factory.sendLIST()	
		d.addCallback(self.gotMasterMetadata)
		d.addErrback(self.errMasterMetadata)
		return d

	def gotMasterMetadata(self, master):
		self.mastermetadata = master

	def errMasterMetadata(self, err):
		print err
		reactor.stop()

	def readFileConfig(self, mtime=None):
		print "reading FileConfig"
		file = open(self.fileconfigfile, 'r')
		self.fileconfig = eval(file.read())
		file.close()
		if mtime:
			self.fileconfigfileMTime = mtime
		else:
			self.fileconfigfileMTime = os.stat(
					self.fileconfigfile)[stat.ST_MTIME]

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
			if file in self.mastermetadata:
				fileChangeTime = self.mastermetadata[file][1]
			else:
				return True
			print "mtime = %s, ctime = %s (%s)" % (mtime, fileChangeTime, file)
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

	def checkFileConfig(self):
		# check config file to see if it has changed, then reparse it
		if not self.fileconfigfile:
			# first time through
			print "checking fileconfigfile (initial)"
			if os.environ.has_key('FLUDHOME'):
				fludhome = os.environ['FLUDHOME']
			elif os.environ.has_key('HOME'):
				fludhome = os.environ['HOME']+"/.flud"
			else:
				fludhome = ".flud"
			# XXX: fludfile.conf should be in config
			self.fileconfigfile = os.path.join(fludhome, "fludfile.conf")
			if os.path.isfile(self.fileconfigfile):
				self.readFileConfig()
				return True
			else:
				print "no fileconfigfile to read"
		elif os.path.isfile(self.fileconfigfile):
			if self.fileChanged(self.fileconfigfile, self.fileconfigfileMTime):
				print "fileconfigfile changed"
				mtime = time.time()
				self.readFileConfig(mtime)
				return True
		return False

	def checkFilesystem(self):
		checkedFiles = set()
		changedFiles = set()

		def checkList(list):
			#print "checkList: %s" % list
			#print "checkedFiles: %s" % checkedFiles
			for entry in list:
				# XXX: if entry is in master metadata, and its mtime is not
				# earlier than the time used by fileChanged, skip it (add 'and'
				# clause)
				if entry not in checkedFiles and \
						entry not in self.fileconfigExcluded and \
						entry not in self.mastermetadata:
					print "checkFilesystem for %s" % entry
					if os.path.isdir(entry):
						#print "dir %s" % entry
						dirfiles = [os.path.join(entry, i) 
								for i in os.listdir(entry)]
						checkedFiles.update([entry,])
						checkList(dirfiles)
					elif self.fileChanged(entry):
						print "%s changed" % entry
						if os.path.isfile(entry):
							changedFiles.update([entry,])
							#print "file %s changed" % entry
						else:
							print "entry ?? %s ?? changed" % entry
					checkedFiles.update([entry,])

		checkList(self.fileconfigSelected)
		self.fileChangeTime = time.time()
		return changedFiles

	def storefileFailed(self, err, file):
		print "storing %s failed: %s" % (file, err)
		err.printTraceback()
		#print dir(err)

	def storefileYay(self, r, file):
		print "storing %s success" % file

	def storeFiles(self, changedFiles):
		#print "storing %s" % changedFiles
		dlist = []
		for f in changedFiles:
			print "storing %s" % f
			deferred = self.factory.sendPUTF(f)
			deferred.addCallback(self.storefileYay, f)
			deferred.addErrback(self.storefileFailed, f)
			dlist.append(deferred)
		dl = defer.DeferredList(dlist)
		return dl
		#return defer.succeed(True)

	def restartCheckTimer(self, v):
		print "restarting timer (%d) to call run()" % CHECKTIME
		reactor.callLater(CHECKTIME, self.run)

	def updateMasterMetadata(self, v):
		return self.getMasterMetadata()

	def run(self):
		print "run"
		self.checkFileConfig()
		changedFiles = self.checkFilesystem()
		print "%s changed" % changedFiles
		d = self.storeFiles(changedFiles)
		d.addBoth(self.updateMasterMetadata)
		d.addBoth(self.restartCheckTimer)

