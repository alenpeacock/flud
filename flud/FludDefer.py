from twisted.python import failure
from twisted.internet import defer

class ErrDeferredList(defer.DeferredList):
	"""
	ErrDeferredList acts just like DeferredList, except that if *any* of the
	Deferreds in the DeferredList errback(), the NewDeferredList also
	errback()s.  This is different from DeferredList(fireOnOneErrback=True) in
	that if you use that method, you only know about the first failure, and you
	won't learn of subsequent failures/success in the list. returnOne indicates
	whether the full result of the DeferredList should be returned, or just the
	first result (or first error)
	"""
	def __init__(self, list, returnOne=False):
		defer.DeferredList.__init__(self, list, consumeErrors=True)
		self.returnOne = returnOne
		self.addCallback(self.wrapResult)

	def wrapResult(self, result):
		#print "DEBUG: result= %s" % result
		for i in result:
			if i[0] == False:
				if self.returnOne:
					raise failure.DefaultException(i[1])
				else:
					raise failure.DefaultException(result)
		if self.returnOne:
			#print "DEBUG: returning %s" % str(result[0][1])
			return result[0][1]
		else:
			#print "DEBUG: returning %s" % result
			return result
