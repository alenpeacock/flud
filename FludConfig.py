"""
FludConfig.py, (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

manages configuration file for flud backup.
"""

import os, sys, socket, re, logging
import ConfigParser
import FludCrypto
from FludCrypto import FludRSA
from FludkRouting import kRouting

""" default mapping of relative URLs """
def_commandmap = {'ID': 'ID', 'GROUPID': 'GROUPID', 'STORE': 'STORE', 
		'RETRIEVE': 'RETRIEVE', 'VERIFY': 'VERIFY', 'PROXY': 'PROXY', 
		'DELETE': 'DELETE', 
		'kFINDNODE': 'kFINDNODE', 'kFINDVAL': 'kFINDVAL', 'kSTORE': 'kSTORE'}

logger = logging.getLogger('flud')

CLIENTPORTOFFSET = 500

class FludDebugLogFilter(logging.Filter):
	"""
	Keeps all logging levels defined by loggers, but ups level to DEBUG for
	loggers whose namespaces match patterns given by wildcards.
	"""
	# XXX: doesn't really interact with all logging levels by all loggers, only
	# with the one defined by the root logger.  If children have stricter
	# loglevels set, this filter won't ever get called on them.

	def __init__(self, wildcardStrings):
		self.setWildcards(wildcardStrings)
		root = logging.getLogger("")
		if hasattr(root, 'fludDebugLogLevel'):
			self.effectiveLevel = root.fludDebugLogLevel
		else:
			self.effectiveLevel = root.getEffectiveLevel()
			self.fludDebugLogLevel = root.getEffectiveLevel()
		root.setLevel(logging.NOTSET)

	def setWildcards(self, wildcardStrings):
		self.wildcards = []
		if not isinstance(wildcardStrings, list):
			wildcardStrings = [wildcardStrings]
		for s in wildcardStrings:
			self.setWildcard(s)

	def setWildcard(self, wildcardString):
		fields = wildcardString.split('.')
		for i, s in enumerate(fields):
			#print "%s:%s" % (i, s)
			if "*" == s:
				fields[i] = r'[\w.]*'
			else:
				try:
					if s.index(s, '*') > 0:
						fields[i] = s.replace('*', r'[\w]*')
				except:
					pass
		regex = "^%s$" % r'\.'.join(fields)
		self.wildcards.append(re.compile(regex))

	def filter(self, record):
		if record.levelno >= self.effectiveLevel:
			return 1
		for w in self.wildcards:
			m = w.match(record.name)
			if m:
				return 1
		return 0

# XXX: refactor out the try/except stuff that could be done with has_key()

class FludConfig:
	"""
	Handles configuration for Flud nodes.  Most persistent settings live in
	this class.  
	
	Configuration is kept in the directory specified by FLUDHOME if this value
	is set in the environment, otherwise in HOME/.flud/.  If no existing
	configuration exists, this object will create a configuration with sane
	default values.
	"""
	def __init__(self):
		self.Kr = 0
		self.Ku = 0
		self.nodeID = 0
		self.groupIDr = 0
		self.groupIDu = 0
		self.port = -1
		self.commandmap = {}
		self.reputations = {}
		self.nodes = {}

		try:
			self.fludhome = os.environ['FLUDHOME']
		except:
			try:
				home = os.environ['HOME']
				self.fludhome = home+"/.flud"
			except:
				logger.warn("cannot determine FLUDHOME.")
				logger.warn("Please set HOME or FLUDHOME environment variable")

		if os.path.isdir(self.fludhome) == False:
			os.mkdir(self.fludhome, 0700)

		self.fludconfig = self.fludhome+"/flud.conf"
		self.configParser = ConfigParser.ConfigParser()
		if os.path.isfile(self.fludconfig) == False:
			conffile = file(self.fludconfig, "w")
		else:
			conffile = file(self.fludconfig, "r")
			self.configParser.readfp(conffile)
		conffile.close()

		logger.info('fludhome = %s' % self.fludhome)
		logger.info('fludconfig = %s' % self.fludconfig)

	def load(self, serverport=None, doLogging=True):
		"""
		If serverport is given, it overrides any value that may be in the
		configuration file
		"""

		self.logfile, self.loglevel = self.getLoggingConf()
		if doLogging:
			if os.path.isfile(self.logfile):
				os.remove(self.logfile)
			handler = logging.FileHandler(self.logfile)
			formatter = logging.Formatter('%(asctime)s %(filename)s:%(lineno)d'
					' %(name)s %(levelname)s: %(message)s', datefmt='%H:%M:%S')
			handler.setFormatter(formatter)
			logger.addHandler(handler)
			logging.getLogger("").setLevel(self.loglevel)
			#logger.setLevel(self.loglevel)
			#logger.setLevel(logging.WARNING) # XXX: overrides user prefs
			#logger.setLevel(logging.DEBUG) # XXX: overrides user prefs
			if os.environ.has_key("FLUDLOGFILTER"):
				self.filter = FludDebugLogFilter(
						os.environ["FLUDLOGFILTER"].split(' '))
				handler.addFilter(self.filter)
				# XXX: add a LocalPrimitive that can be called dynamically to
				# invoke filter.setWildcards()

		self.Kr, self.Ku, self.nodeID, self.groupIDr, self.groupIDu \
				= self.getID()
		logger.debug('Kr = %s' % self.Kr.exportPrivateKey())
		logger.debug('Ku = %s' % self.Ku.exportPublicKey())
		logger.debug('nodeID = %s' % self.nodeID)
		logger.debug('groupIDr = %s' % self.groupIDr)
		logger.debug('groupIDu = %s' % self.groupIDu)
		
		self.port, self.clientport, self.commandmap = self.getServerConf()
		if serverport != None:
			self.port = serverport
			self.clientport = serverport + CLIENTPORTOFFSET
			self.configParser.set("server","port",self.port)
			self.configParser.set("server","clientport",self.clientport)
		logger.debug('port = %s' % self.port)
		logger.debug('clientport = %s' % self.clientport)
		logger.debug('commandmap = %s' % self.commandmap)

		self.routing = kRouting((socket.getfqdn(), self.port,
				long(self.nodeID, 16), self.Ku.exportPublicKey()['n']))

		self.storedir, self.generosity, self.minoffer = self.getStoreConf()
		if os.path.isdir(self.storedir) == False:
			os.mkdir(self.storedir)
			os.chmod(self.storedir, 0700)
		logger.debug('storedir = %s' % self.storedir)

		self.kstoredir = self.getkStoreConf()
		if os.path.isdir(self.kstoredir) == False:
			os.mkdir(self.kstoredir)
			os.chmod(self.kstoredir, 0700)
		logger.debug('kstoredir = %s' % self.kstoredir)

		self.clientdir = self.getClientConf()
		if os.path.isdir(self.clientdir) == False:
			os.mkdir(self.clientdir)
			os.chmod(self.clientdir, 0700)
		logger.debug('clientdir = %s' % self.clientdir)

		self.metadir, self.metamaster = self.getMetaConf()
		if os.path.isdir(self.metadir) == False:
			os.mkdir(self.metadir)
			os.chmod(self.metadir, 0700)
		logger.debug('metadir = %s' % self.metadir)

		self.reputations = self.getReputations()
		logger.debug("reputations = %s" % str(self.reputations))
		
		self.nodes = self.getKnownNodes()
		logger.debug("known nodes = %s" % str(self.nodes))

		self.save()
		os.chmod(self.fludconfig, 0600)

	def save(self):
		conffile = file(self.fludconfig, "w")
		self.configParser.write(conffile) 
		conffile.close()

	def addNode(self, nodeID, host, port, Ku, mygroup=None):
		"""
		Convenience method for adding a node to the known.
		If a node with nodeID already exists, nothing changes.
		This method /does not/ save the new configuration to file,
		"""
		if mygroup == None:
			mygroup = self.groupIDu
		if self.nodes.has_key(nodeID) == False:
			self.nodes[nodeID] = {'host': host, 'port': port, 
					'Ku': Ku.exportPublicKey(), 'mygroup': mygroup}
			#logger.log(logging.DEBUG, "nodes: " % str(self.nodes))
			# XXX: disabled nodes saving
			#for k in self.nodes:
			#	self.configParser.set('nodes', k, self.nodes[k])
			n = self.routing.insertNode((host, int(port), long(nodeID, 16), 
				Ku.exportPublicKey()['n']))
			if n != None:
				logger.warn("need to ping %s for LRU in routing table!" 
						% str(n))
				# XXX: instead of pinging, put it in a replacement cache table
				#      and when one of the nodes needs replaced (future query)
				#      replace it with one of these. Sec 4.1
			# XXX: should also create a corresponding reputation

	def getLoggingConf(self):
		"""
		Returns logging configuration: logfile and loglevel 
		"""
		if (self.configParser.has_section("logging") == False):
			self.configParser.add_section("logging")
		
		try:
			logfile = int(self.configParser.get("logging","logfile"))
		except:
			logger.debug("no logfile specified, using default")
			logfile = self.fludhome+'/flud.log'
		self.configParser.set("logging", "logfile", logfile)

		try:
			loglevel = int(self.configParser.get("logging","loglevel"))
			#loglevel = logging.WARNING # XXX: remove me
		except:
			logger.debug("no loglevel specified, using default")
			loglevel = logging.WARNING
		self.configParser.set("logging", "loglevel", loglevel)

		return logfile, loglevel 

		
	def getID(self):
		"""
		Returns a tuple: private key, public key, nodeID, private group ID, and
		public group ID from config.  If these values don't exist in conf file,
		they are generated and added.
		"""
		# get the keys and IDs from the config file.
		# If these values don't exist, generate a pub/priv key pair, nodeID,
		# and groupIDs.
		if (self.configParser.has_section("identification") == False):
			self.configParser.add_section("identification")
		
		try:
			privkey = FludRSA.importPrivateKey( 
					eval(self.configParser.get("identification","Kr"))) 
		except:
			pubkey, privkey = FludCrypto.generateKeys()
		else:
			try:
				pubkey = FludRSA.importPublicKey( 
						eval(self.configParser.get("identification","Ku")))
			except:
				pubkey = privkey.publickey()
			
		try:
			nodeID = self.configParser.get("identification","nodeID") 
		except:
			#nodeID = FludCrypto.hashstring(str(pubkey.exportPublicKey()))
			nodeID = pubkey.id()
		
		try:
			privgroupID = self.configParser.get("identification",
					"groupIDr")[:64]
		except:
			privgroupID = 'fludtest' # default groupID hardcoded
		
		try:
			pubgroupID = self.configParser.get("identification","groupIDu") 
		except:
			pubgroupID = FludCrypto.hashstring(str(pubkey.exportPublicKey()) 
					+privgroupID)

		# write the settings back out to config object
		self.configParser.set("identification","Kr",privkey.exportPrivateKey())
		self.configParser.set("identification","Ku",pubkey.exportPublicKey())
		self.configParser.set("identification","nodeID",nodeID)
		self.configParser.set("identification","groupIDr",privgroupID)
		self.configParser.set("identification","groupIDu",pubgroupID)
		
		# return the values
		return privkey, pubkey, nodeID, privgroupID, pubgroupID

	def getServerConf(self):
		"""
		Returns server configuration: port number
		"""
		if (self.configParser.has_section("server") == False):
			self.configParser.add_section("server")
		
		try:
			port = int(self.configParser.get("server","port"))
		except:
			logger.debug("no port specified, using default")
			port = 8080 # XXX: default should be defined elsewhere.
			            #      Should prefer 80.  If in use, use 8080+ 
		
		try:
			clientport = int(self.configParser.get("server","clientport"))
		except:
			logger.debug("no clientport specified, using default")
			clientport = port+CLIENTPORTOFFSET 
		
		try:
			commandmap = eval(self.configParser.get("server","commandmap"))
		except:
			logger.debug("no commandmap specified, using default")
			commandmap = def_commandmap
		for i in def_commandmap: # ensure that commandmap covers all keys
			try:
				j = commandmap[i]
			except:
				commandmap[i] = def_commandmap[i]

		# XXX: could also do a 'parammap'

		self.configParser.set("server","port",port)
		self.configParser.set("server","clientport",clientport)
		self.configParser.set("server","commandmap",commandmap)

		return port, clientport, commandmap

	def _getDirConf(self, configParser, section, default):
		if (configParser.has_section(section) == False):
			configParser.add_section(section)
		
		try:
			dir = int(self.configParser.get(section,"dir"))
		except:
			logger.debug("no %s directory specified, using default", section)
			dir = self.fludhome+'/'+default

		if not os.path.isdir(dir):
			os.makedirs(dir)

		self.configParser.set(section,"dir",dir)

		return dir 

	def getClientConf(self):
		"""
		Returns client configuration: download directory 
		"""
		return self._getDirConf(self.configParser, "client", "dl") 

	def getStoreConf(self):
		"""
		Returns data store configuration
		"""
		storedir = self._getDirConf(self.configParser, "store", "store")
		try:
			generosity = self.configParser.get("store", "generosity")
		except:
			logger.debug("no generosity specified, using default")
			generosity = 1.5
		try:
			minoffer = self.configParser.get("store", "minoffer")
		except:
			logger.debug("no minoffer specified, using default")
			minoffer = 1024
		return storedir, generosity, minoffer

	def getkStoreConf(self):
		"""
		Returns dht data store configuration
		"""
		return self._getDirConf(self.configParser, "kstore", "dht")

	def getMetaConf(self):
		"""
		Returns metadata configuration: metadata directory 
		"""
		metadir = self._getDirConf(self.configParser, "metadata", "meta")
		
		try:
			master = self.configParser.get("meta","master")
		except:
			logger.debug("no meta master file specified, using default")
			master = "master"

		if not os.path.isfile(metadir+'/'+master):
			f = open(metadir+'/'+master, 'w')
			f.close()
		
		return (metadir, master)

	def getReputations(self):
		"""
		Returns dict of reputations known to this node
		"""
		# XXX: should probably just throw these in with 'nodes' (for efficiency)
		return self._getDict(self.configParser, "reputations")

	def getKnownNodes(self):
		"""
		Returns dict of nodes known to this node
		"""
		return {}
		# XXX: don't read known nodes for now
		result = self._getDict(self.configParser, "nodes")
		for i in result:
			print str(i)
			self.routing.insertNode( 
					(result[i]['host'], result[i]['port'], long(i, 16), 
						result[i]['nKu']))
		return result

	def _getDict(self, configParser, section):
		"""
		creates a dictionary from the list of pairs given by 
		ConfigParser.items(section).  Requires that the right-hand side of
		the config file's "=" operator be a valid python type, as eval()
		will be invoked on it
		"""
		if (configParser.has_section(section) == False):
			configParser.add_section(section)
		
		try:
			items = configParser.items(section)
			result = {}
			for item in items:
				#print item
				try:
					result[str(item[0])] = eval(item[1])
					configParser.set(section, item[0], item[1])
				except:
					logger.warn("item '%s' in section '%s'"
							" of the config file has an unreadable format" 
							% str(item[0]), str(section))
		except:
			logger.warn("Couldn't read %s from config file:" % section)

		return result
		
	def _test(self):
		import doctest
		doctest.testmod()

if __name__ == '__main__':
	fludConfig = FludConfig()
	fludConfig._test()
