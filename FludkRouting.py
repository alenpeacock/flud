"""
FludkRouting.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

Implements kademlia-style kbuckets (the routing table for the DHT layer).

Although this is not a derivative of Khashmir (written by Andrew Loewenstern,
Aaron Swartz, et. al.), we would like to give Khashmir a nod for inspiring
portions of the design.  Khashmir is distributed under the MIT License and is a
very nice piece of work.  Take a look at http://khashmir.sourceforge.net/ for
more information.
"""

from bisect import *
import logging

#k = 5          # This is the max depth of a kBucket
k = 12         # This is the max depth of a kBucket and the replication factor
		       # XXX: need to split out k into two vars
a = 3          # alpha, the system-wide concurrency parameter
idspace = 256  # using sha-256

logger = logging.getLogger("flud.k")

def kCompare(a, b, target):
	"""
	Uses the XOR metric to compare target to a and b (useful for sorting)
	@param a an integer (or long) value
	@param b an integer (or long) value
	@param target the target ID as an integer (or long) value
	@return 1 if b > a, -1 if a < b, 0 if a == b

	>>> l = [1, 2, 23, 14, 5, 4, 5, 3, 20]
	>>> l.sort(lambda a, b: kCompare(a, b, 5))
	>>> l
	[5, 5, 4, 1, 3, 2, 14, 20, 23]
	"""
	x, y = target^a, target^b
	if x == y:
		return 0
	return int((x - y) / abs(x - y))


class kRouting:
	"""
	Contains the kBuckets for this node.  Provides methods for inserting,
	updating, and removing nodes.  Most importantly, performs kademlia-style
	routing by returning the node[s] closest to a particular id.
	
	>>> table = kRouting(('1.2.3.4', 34, 123456), 20, 5)
	>>> table.insertNode(('2.2.3.4', 34,  23456))
	>>> table.insertNode(('3.2.3.4', 34, 223456))
	>>> table.insertNode(('4.2.3.4', 34, 723456))
	>>> table.insertNode(('5.2.3.4', 34, 423456))
	>>> table.insertNode(('6.2.3.4', 34, 323456))
	>>> table.kBuckets
	[{'0-80000': [('1.2.3.4', 34, 123456), ('2.2.3.4', 34, 23456), ('3.2.3.4', 34, 223456), ('5.2.3.4', 34, 423456), ('6.2.3.4', 34, 323456)]}, {'80001-100000': [('4.2.3.4', 34, 723456)]}]
	>>> table.findNode(23456)
	[('2.2.3.4', 34, 23456), ('1.2.3.4', 34, 123456), ('3.2.3.4', 34, 223456), ('6.2.3.4', 34, 323456), ('5.2.3.4', 34, 423456)]
	>>> table.findNode(55555)
	[('2.2.3.4', 34, 23456), ('1.2.3.4', 34, 123456), ('3.2.3.4', 34, 223456), ('6.2.3.4', 34, 323456), ('5.2.3.4', 34, 423456)]
	>>> table.findNode(722222)
	[('4.2.3.4', 34, 723456), ('3.2.3.4', 34, 223456), ('1.2.3.4', 34, 123456), ('2.2.3.4', 34, 23456), ('5.2.3.4', 34, 423456)]
	>>> table.insertNode(('7.2.3.4', 34, 733456))
	>>> table.insertNode(('8.2.3.4', 34, 743456))
	>>> table.insertNode(('9.2.3.4', 34, 753456))
	>>> table.insertNode(('10.2.3.4', 34, 763456))
	>>> table.insertNode(('11.2.3.4', 34, 773456))
	('4.2.3.4', 34, 723456)
	>>> table.replaceNode(('4.2.3.4', 34, 723456), ('11.2.3.4', 34, 773456))
	>>> table.kBuckets
	[{'0-80000': [('1.2.3.4', 34, 123456), ('2.2.3.4', 34, 23456), ('3.2.3.4', 34, 223456), ('5.2.3.4', 34, 423456), ('6.2.3.4', 34, 323456)]}, {'80001-100000': [('7.2.3.4', 34, 733456), ('8.2.3.4', 34, 743456), ('9.2.3.4', 34, 753456), ('10.2.3.4', 34, 763456), ('11.2.3.4', 34, 773456)]}]
	>>> table.removeNode(('1.2.3.4', 34, 123456))
	>>> table.kBuckets
	[{'0-80000': [('2.2.3.4', 34, 23456), ('3.2.3.4', 34, 223456), ('5.2.3.4', 34, 423456), ('6.2.3.4', 34, 323456)]}, {'80001-100000': [('7.2.3.4', 34, 733456), ('8.2.3.4', 34, 743456), ('9.2.3.4', 34, 753456), ('10.2.3.4', 34, 763456), ('11.2.3.4', 34, 773456)]}]
	>>> table.knownNodes()
	[('2.2.3.4', 34, 23456), ('3.2.3.4', 34, 223456), ('5.2.3.4', 34, 423456), ('6.2.3.4', 34, 323456), ('7.2.3.4', 34, 733456), ('8.2.3.4', 34, 743456), ('9.2.3.4', 34, 753456), ('10.2.3.4', 34, 763456), ('11.2.3.4', 34, 773456)]
	>>> table.knownExternalNodes()
	[('2.2.3.4', 34, 23456), ('3.2.3.4', 34, 223456), ('5.2.3.4', 34, 423456), ('6.2.3.4', 34, 323456), ('7.2.3.4', 34, 733456), ('8.2.3.4', 34, 743456), ('9.2.3.4', 34, 753456), ('10.2.3.4', 34, 763456), ('11.2.3.4', 34, 773456)]
	"""
	def __init__(self, node, bits=idspace, depth=k):
		"""
		@param node a (ip, port, id) triple, where id is an int (this is 
		needed to know when to split a bucket).
		"""
		self.k = depth
		self.kBuckets = [kBucket(0, 2**bits, depth),]
		#self.kBuckets = [kBucket(0, 1, depth),]
		#for i in xrange(1,bits):
		#	self.kBuckets.append(kBucket(2**i, 2**(i+1)-1, depth))
		self.insertNode(node)
		self.node = node
	
	def insertNode(self, node):
		"""
		Inserts a node into the appropriate kBucket.  If the node already
		exists in the appropriate kBucket, it is moved to the tail of the list.
		If the bucket is full, this method returns the oldest node, which the
		caller should then ping.  If the oldest node is alive, the caller
		does nothing.  Otherwise, the caller should call replaceNode.
		@param node a (ip, port, id) triple, where id is a long.
		"""
		if len(node) < 3:
			raise ValueError("node must be a triple (ip, port, id)")
		id = node[2]
		bucket = self._findBucket(id)
		try:
			# XXX: need to transfer key/vals that belong to new node?
			bucket.updateNode(node)
		except BucketFullException, e:
			if (bucket.begin <= self.node[2] < bucket.end):
				# bucket is full /and/ the local node is in this bucket, 
				# split and try adding it again.
				self._splitBucket(bucket)
				self.insertNode(node)
				logger.debug("split and added %x" % node[2])
				return
			# XXX: need to also split for some other cases, see sections 2.4 
			# and 4.2.
			else:
				# bucket is full but we won't split.  Return the oldest node
				# so that the caller can determine if it should be expunged.
				# If the old node is not reachable, caller should call 
				# replaceNode()
				logger.debug("didn't add %x" % node[2])
				return bucket.contents[0]
			logger.debug("didn't add %x" % node[2])
			return bucket.contents[0]

	def removeNode(self, node):
		"""
		Invalidates a node.
		"""
		bucket = self._findBucket(node[2])
		bucket.delNode(node)
		
	def replaceNode(self, replacee, replacer):
		"""
		Expunges replacee from its bucket, making room to add replacer 
		"""
		# XXX: constraint checks: replacee & replacer belong to the same bucket,
		#      bucket is currently full, adding replacer doesn't overfill, etc.
		self.removeNode(replacee)
		self.insertNode(replacer)

	def findNode(self, nodeID):
		"""
		Returns k closest node triples with which the caller may make
		additional queries.  If nodeID is found, it will be the first result.
		@param nodeID an int
		"""
		nodes = []
		bucket = self._findBucket(nodeID)
		#n = bucket.findNode(nodeID)
		#if n != None: 
		#	nodes.append(n)

		nodes += bucket.contents
		if len(nodes) < self.k:
			nextbucket = self._nextbucket(bucket)
			prevbucket = self._prevbucket(bucket)
			while len(nodes) < self.k \
					and (nextbucket != None or prevbucket != None):
				if nextbucket != None:
					nodes += nextbucket.contents
				if prevbucket != None: 
					nodes += prevbucket.contents
				nextbucket = self._nextbucket(nextbucket)
				prevbucket = self._prevbucket(prevbucket)
			
		nodes.sort(lambda a, b, n=nodeID: cmp(n ^ a[2], n ^ b[2]))
		return nodes[:self.k]

	def findNodeOld(self, nodeID):
		"""
		Attempts to find the given node, returning a <ip, port, id> triple.  
		If the node is not found locally, returns k closest node triples with
		which the caller may make additional queries.
		@param nodeID an int
		"""
		bucket = self._findBucket(nodeID)
		n = bucket.findNode(nodeID)
		if n != None: 
			return (n,)

		# nodeID isn't in our routing table, so return the k closest matches
		nodes = []
		nodes += bucket.contents
		if len(nodes) < self.k:
			nextbucket = self._nextbucket(bucket)
			prevbucket = self._prevbucket(bucket)
			while len(nodes) < self.k \
					and (nextbucket != None or prevbucket != None):
				if nextbucket != None:
					nodes += nextbucket.contents
				if prevbucket != None: 
					nodes += prevbucket.contents
				nextbucket = self._nextbucket(nextbucket)
				prevbucket = self._prevbucket(prevbucket)
			
		nodes.sort(lambda a, b, n=nodeID: cmp(n ^ a[2], n ^ b[2]))
		return nodes[:self.k]

	def updateNode(self, node):
		"""
		Call to update a node, i.e., whenever the node has been recently seen
		@param node a (ip, port, id) triple, where id is an int.
		"""
		self.insertNode(node)

	def knownExternalNodes(self):
		result = []
		for i in self.kBuckets:
			for j in i.contents:
				if j[2] != self.node[2]:
					result.append(j)
		return result

	def knownNodes(self):
		result = []
		for i in self.kBuckets:
			for j in i.contents:
				result.append(j)
		return result

	def _nextbucket(self, bucket):
		if bucket == None:
			return bucket
		i = self.kBuckets.index(bucket)+1
		if i >= len(self.kBuckets):
			return None
		return self.kBuckets[i]

	def _prevbucket(self, bucket):
		if bucket == None:
			return bucket
		i = self.kBuckets.index(bucket)-1
		if i < 0:
			return None
		return self.kBuckets[i]

	def _findBucket(self, i):
		"""
		returns the bucket which would contain i.
		@param i an int
		"""
		#print "kBuckets = %s" % str(self.kBuckets)
		bl = bisect_left(self.kBuckets, i)
		if bl >= len(self.kBuckets):
			raise Exception(
					"tried to find an ID that is larger than ID space: %s" % i)	
		return self.kBuckets[bisect_left(self.kBuckets, i)]
	
	def _splitBucket(self, bucket):
		"""
		This is called for the special case when the bucket is full and this 
		node is a member of the bucket.  When this occurs, the bucket should
		be split into two new buckets.
		"""
		halfpoint = (bucket.end - bucket.begin) / 2
		newbucket = kBucket(bucket.end - halfpoint + 1, bucket.end, self.k)
		self.kBuckets.insert(self.kBuckets.index(bucket.begin) + 1, newbucket)
		bucket.end -= halfpoint

		for node in bucket.contents[:]:
			if node[2] > bucket.end:
				bucket.delNode(node)
				newbucket.addNode(node)


class kBucket:
	"""
	A kBucket is a list of <ip, port, id> triples, ordered according to time
	last seen (most recent at tail).  Every kBucket has a begin and end
	number, indicating the chunk of the id space that it contains.
	
	>>> b = kBucket(0,100,5)
	>>> b
	{'0-64': []}
	>>> n1 = ('1.2.3.4', 45, 'd234a53546e4c23')
	>>> n2 = ('10.20.30.40', 45, 'abcd234a53546e4')
	>>> n3 = ('10.20.30.4', 5, 'abcd')
	>>> b.addNode(n1)
	>>> b
	{'0-64': [('1.2.3.4', 45, 'd234a53546e4c23')]}
	>>> b.addNode(n2)
	>>> b
	{'0-64': [('1.2.3.4', 45, 'd234a53546e4c23'), ('10.20.30.40', 45, 'abcd234a53546e4')]}
	>>> b.addNode(n1)
	>>> b
	{'0-64': [('10.20.30.40', 45, 'abcd234a53546e4'), ('1.2.3.4', 45, 'd234a53546e4c23')]}
	>>> b.delNode(n3)
	>>> b
	{'0-64': [('10.20.30.40', 45, 'abcd234a53546e4'), ('1.2.3.4', 45, 'd234a53546e4c23')]}
	>>> b.addNode(n2)
	>>> b
	{'0-64': [('1.2.3.4', 45, 'd234a53546e4c23'), ('10.20.30.40', 45, 'abcd234a53546e4')]}
	>>> b.updateNode(n1)
	>>> b
	{'0-64': [('10.20.30.40', 45, 'abcd234a53546e4'), ('1.2.3.4', 45, 'd234a53546e4c23')]}
	>>> b.delNode(n2)
	>>> b
	{'0-64': [('1.2.3.4', 45, 'd234a53546e4c23')]}
	>>> b.addNode(n3)
	>>> f = b.findNode(n3[2])
	>>> f == n3
	True
	>>> c = kBucket(101,200,5)
	>>> d = kBucket(150,250,5)       # wouldn't really have overlap in practice
	>>> e = kBucket(251, 2**256,5) 	
	>>> buckets = (b, c, d, e)     # if not added insort, must sort for bisect
	>>> b1 = b
	>>> b1 == b
	True
	>>> b1 != b
	False
	>>> b == 50
	True
	>>> b == 0
	True
	>>> b == 100
	True
	>>> b == -1
	False
	>>> b > -1
	True
	>>> b == 101
	False
	>>> b < 101
	True
	>>> b <= 90
	True
	>>> b <= 100
	True
	>>> b <= 101
	True
	>>> b < d
	True
	>>> b <= c
	True
	>>> b > c
	False
	>>> bisect_left(buckets, 98)
	0
	>>> bisect_left(buckets, 198)
	1
	>>> bisect_left(buckets, 238)
	2
	>>> bisect_left(buckets, 298)
	3
	"""
	
	def __init__(self, begin, end, depth=k):
		self.k = depth
		self.begin = begin
		self.end = end
		self.contents = []

	def __repr__(self):
		return "{'%x-%x': %s}" % (self.begin, self.end, self.contents)
		#return "{'"+repr(self.begin)+'-'+repr(self.end)+"': "\
		#		+repr(self.contents)+"}"
		#return "<kBucket "+repr(self.begin)+'-'+repr(self.end)+": "\
		#		+repr(self.contents)+">"

	def addNode(self, node):
		""" adds the given node to this bucket. If the node is already a member
		of this bucket, its position is updated to the end of the list.  If the
		bucket is full, raises an exception
		"""
		if node in self.contents:
			self.contents.remove(node)
			self.contents.append(node)
		elif len(self.contents) >= self.k:
			raise BucketFullException()
		else:
			ids = [x[2] for x in self.contents]
			if node[2] in ids:
				# remove the matching node's old contact info
				self.contents.pop(ids.index(node[2]))
			self.contents.append(node)

	def updateNode(self, node):
		""" Moves the given node to the tail of the list.  If the node isn't
		present in this bucket, this method attempts to add it by calling
		addNode (which may throw a BucketFullException if bucket is full)
		"""
		self.addNode(node)

	def delNode(self, node):
		""" removes the given node, if present, from this bucket """
		try:
			self.contents.remove(node)
		except:
			pass
	
	def findNode(self, nodeID):
		for i in self.contents:
			if i[2] == nodeID:
				return i
		return None

	# The following comparators allow us to use list & bisect on the buckets.
	# integers, longs, and buckets all may be compared to a bucket.
	def __eq__(self, i):
		return i >= self.begin and self.end >= i
	def __ne__(self, i):
		return i < self.begin or self.end < i
	def __lt__(self, i):
		return self.end < i
	def __le__(self, i):
		return self.begin <= i
	def __gt__(self, i):
		return self.begin > i
	def __ge__(self, i):
		return self.end >= i


class BucketFullException(Exception):
	pass
	

def _test():
	import doctest
	doctest.testmod()

if __name__ == '__main__':
	_test()
