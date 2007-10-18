
# XXX: this class goes away

class Reputation:
	"""
	Each node maintains a list of reputation
	objects corresponding to reputations of other nodes.  Reputations may be
	self-generated (in which case the originator is this node itself), or may 
	be relayed (in which case some other node is the originator).  
	Self-generated reputations are vastly more reliable than those relayed --
	relayed reputations are second-hand information, and are more likely to
	have false data.
	"""

	def __init__(self, ID, originator):
		"""
		Variables designated as '%' have values between 0 and 100.
		"""
		self.ID = ID
		self.originator = originator
		self.confidence = 0 	# % originator data stored / nodes the 
		                    	# originator stores to
		self.verifiability = 0	# % originator data verified success/failed
		self.availability = 0	# % originator contact attempts success/fail
		self.bandwidth = 0		# avg bandwidth observed from orig. to ID.
		self.age = 0			# age of reputation in days

	def score(self):
		"""
		Returns a score for this reputation based in member variables.  The
		reputation must be a local reputation, i.e., the originator must
		be equal to the global myNodeID.  Otherwise, call scoreRelay()

		>>> myNodeID = "self"
		>>> rep = Reputation("somenode","self")
		>>> rep.availability = 50
		>>> rep.verifiability = 50
		>>> rep.score()
		33
		>>> rep = Reputation("somenode","someothernode")
		>>> rep.availability = 30
		>>> rep.score()
		-1
		"""
		# should find a good adjustment of weights (XXX: machine learning?)
		if self.originator != myNodeID:
			return -1
		return (self.confidence + self.verifiability + self.availability) / 3
		# XXX: should also include age and bandwidth

	def scoreRelay(self):
		"""
		Returns a score for this reputation based in member variables.  The
		reputation must be a remote reputation, i.e., the originator must
		not be equal to the global myNodeID.  Otherwise, call score()

		>>> myNodeID = "self"
		>>> rep = Reputation("somenode","self")
		>>> rep.availability = 50
		>>> rep.verifiability = 50
		>>> rep.scoreRelay()
		-1
		>>> rep = Reputation("somenode","someothernode")
		>>> rep.availability = 30
		>>> rep.scoreRelay()
		10
		"""
		if self.originator == myNodeID:
			return -1
		return (self.confidence + self.verifiability + self.availability) / 3
		# XXX: should also include age and bandwidth

	def updateConfidence(self, totalDataStored, totalNodesStoredTo):
		self.confidence = totalDataStored / totalNodesStoredTo; 

	def _test(self):
		import doctest
		doctest.testmod()
	
if __name__ == '__main__':
	myNodeID = "self"
	rep = Reputation("other", "self")
	rep._test()
