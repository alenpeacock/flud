import urlparse, os, types

from twisted.web import client
from twisted.internet import reactor, defer
from twisted.python import failure

"""
HTTPMultipartDownloader.py (c) 2003-2006 Alen Peacock.  This program is
distributed under the terms of the GNU General Public License (the GPL).

HTTPMultipartDownloader will download mulitple files from a multipart/related.
Note that it does this by using the Content-ID and Content-Length headers in
each multipart, and will fail if those are not present (this could be
genericized to operate without those fields without too much effort)

This code is modeled after twisted.web.client.HTTPDownloader, which is 
copyright 2001-2004 Twisted Matrix Laboratories, MIT licensed.
"""

class HTTPMultipartDownloader(client.HTTPDownloader):
	"""Download multiple files, via multipart/related."""

	protocol = client.HTTPPageDownloader
	value = None

	def __init__(self, url, dir, method='GET', postdata=None, headers=None, 
			agent="Flud client", supportPartial=0):
		self.requestedPartial = 0

		self.filenames = []
		self.dir = dir
		client.HTTPClientFactory.__init__(self, url, method=method, 
				postdata=postdata, headers=headers, agent=agent)
		self.deferred = defer.Deferred()
		self.waiting = 1

	def gotHeaders(self, headers):
		if self.requestedPartial:
			contentRange = headers.get("content-range", None)
			if not contentRange:
				# server doesn't support partial requests, oh well
				self.requestedPartial = 0 
				return
			start, end, realLength = http.parseContentRange(contentRange[0])
			if start != self.requestedPartial:
				# server is acting wierdly
				self.requestedPartial = 0

	def openFile(self, partialContent):
		if partialContent:
			file = open(self.filename, 'rb+')
			file.seek(0, 2)
		else:
			file = open(self.filename, 'wb')
		self.filenames.append(self.filename)
		return file

	def pageStart(self, partialContent):
		"""Called on page download start.

		@param partialContent: tells us if the download is partial download we
		requested.
		"""
		if partialContent and not self.requestedPartial:
			raise ValueError, "we shouldn't get partial content response if"\
					" we didn't want it!"
		self.partialContent = partialContent
		if self.waiting:
			self.waiting = 0
		self.inSubHeader = True
		self.file = None
		self.boundary = None

	def getSubHeader(self, data):
		newboundary = data[:data.find('\r\n')]
		data = data[len(newboundary)+2:]
		if not self.boundary:
			self.boundary = newboundary
		if self.boundary != newboundary:
			if self.boundary+"--" == newboundary:
				# end of multiparts
				return
			else:
				raise ValueError, "found illegal boundary"
				# XXX: print some of newboundary *safely*
				#raise ValueError, "found illegal boundary: %s, was %s" \
				#		% (newboundary[:80], self.boundary)
		headerEnd = data.find('\r\n\r\n')
		if headerEnd != -1:
			self.inSubHeader = False
			self.subHeaders = {}
			headers = data[:headerEnd].split('\r\n')
			for header in headers:
				k, v = header.split(':',1)
				self.subHeaders[k.lower()] = v.lstrip(' ')
			if not self.subHeaders.has_key('content-id'):
				raise ValueError, "no Content-ID field in multipart,"\
						" can't continue"
			# XXX: need to check for badness (e.g, "../../) in content-id
			self.filename = os.path.join(self.dir, 
					self.subHeaders['content-id'])
			self.file = self.openFile(self.partialContent)
			if not self.subHeaders.has_key('content-length'):
				raise ValueError, "no Content-Length field in multipart,"\
						" can't continue"
			self.filesizeRemaining = int(self.subHeaders['content-length'])
			self.pagePart(data[headerEnd+4:])


	def pagePart(self, data):
		if self.inSubHeader:
			self.getSubHeader(data)
		else:
			if not self.file:
				raise ValueError, "file %s not open for output" % self.filename
			try:
				if self.filesizeRemaining > len(data):
					self.file.write(data)
					self.filesizeRemaining -= len(data)
				else:
					self.file.write(data[:self.filesizeRemaining])
					skipto = self.filesizeRemaining
					self.filesizeRemaining = 0
					self.file.close()
					self.file = None
					self.inSubHeader = True
					self.getSubHeader(data[skipto+2:])
			except IOError:
				#raise
				self.file = None
				self.deferred.errback(failure.Failure())

	def pageEnd(self):
		if self.file:
			try:
				self.file.close()
			except IOError:
				self.deferred.errback(failure.Failure())
				return
		self.deferred.callback(self.filenames)

def doit():
	factory = HTTPMultipartDownloader("/ret", "/tmp/")
	reactor.connectTCP('localhost', 1080, factory)
	return factory.deferred

def didit(r):
	print "didit: %s" % str(r)
	reactor.stop()

if __name__ == "__main__":
	# tries to request http://localhost:1080/ret, which it expects to be
	# multipart/related with Content-Length headers
	d = doit()
	d.addBoth(didit)
	reactor.run()
