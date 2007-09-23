"""
FludPrimitiveCLI.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL).

A very primitive command-line interface client to FludNode.py.  Can perform
all basic operations.
"""

import time
from flud.FludCrypto import FludRSA

def _default_oldvals(nlist, olist):
	"""
	@param nlist list of new values
	@param olist list of old values

	>>> nlist = ('', '', 'newval3')
	>>> olist = ('oldval1', 'oldval2', 'oldval3')
	>>> _default_oldvals(nlist, olist)
	('oldval1', 'oldval2', 'newval3')
	"""
	if len(nlist) != len(olist):
		raise ValueError("args to _default_oldvals must be of same length")
	result = []
	for i,j in zip(nlist, olist):
		if isinstance(i, str) and i == '':
			r = j
		else:
			r = i
		result.append(r)
	return tuple(result)
	

def runCLI(client, node):
	"""
	Provides a rudimentary CLI for creating requests.  It understands the
	following commands: getid, challenge, group, store, retrieve, verify,
	kfindnode, kfindvalue, kstore, knownnodes, help, exit
	When a command is entered, 'subshells' are presented asking for each
	command's parameter values, in sequence.  The CLI remembers past values,
	so that if the user skips a value by pressing <return>, the last entered 
	value will be used instead.
	"""

	def errhdlr(error, command=None):
		print "'%s' resulted in error: %s" % (command, error)

	def r_getid(nKu):
		print "nKu = %s" % nKu.exportPublicKey()
		print "id = %s" % nKu.id()

	def r_store(n):
		print "store passed"

	def r_challenge(n):
		print "challenge passed"

	def r_group(n):
		print "group passed"

	def r_getkfindnode(n):
		print "nodes = %s" % n 

	def r_getkstore(n):
		print "stored" 

	def r_getkfindvalue(n):
		print "val = %s" % n 


	import sys
	done = False
	time.sleep(1)
	host = port = nKu = nid = val = file = mdata = ''
	while not done:
		command = raw_input("flud command> ")
		ohost = host
		oport = port
		onKu = nKu
		onid = nid
		oval = val
		ofile = file
		omdata = mdata
		try:
			if command == 'getid':
				host = raw_input("host> ")
				port = raw_input("port> ")
				(host, port) = _default_oldvals((host, port), (ohost, oport))
				command = 'sendGetID("%s", %s)' % (host, port)
				exec('d = client.%s' % command)
				exec('d.addCallback(r_getid)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'challenge':
				host = raw_input("host> ")
				port = raw_input("port> ")
				nKu = raw_input("nKu> ")
				(host, port, nKu) = _default_oldvals((host, port, nKu),
						(ohost, oport, onKu))
				nKu_i = FludRSA.importPublicKey(eval(nKu))
				command = 'sendChallenge(nKu_i, "%s", %s)' % (host, port)
				exec('d = client.%s' % command)
				exec('d.addCallback(r_challenge)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'group':
				host = raw_input("host> ")
				port = raw_input("port> ")
				nKu = raw_input("nKu> ")
				(host, port, nKu) = _default_oldvals((host, port, nKu),
						(ohost, oport, onKu))
				nKu_i = FludRSA.importPublicKey(eval(nKu))
				command = 'sendGroupChallenge(nKu_i, "%s", %s)' % (host, port)
				exec('d = client.%s' % command)
				exec('d.addCallback(r_group)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'store':
				host = raw_input("host> ")
				port = raw_input("port> ")
				nKu = raw_input("nKu> ")
				file = raw_input("filename> ")
				mdata = raw_input("metadata> ")
				(host, port, nKu, file) = _default_oldvals(
						(host, port, nKu, file, mdata),
						(ohost, oport, onKu, ofile, omdata))
				nKu_i = FludRSA.importPublicKey(eval(nKu))
				command = 'sendStore(nKu_i, "%s", %s, "%s")' % (host, port, 
						file, mdata)
				exec('d = client.%s' % command)
				exec('d.addCallback(r_store)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'retrieve':
				print "operation not yet implemented"
			elif command == 'verify':
				print "operation not yet implemented"
			elif command == 'kfindnode':
				host = raw_input("host> ")
				port = raw_input("port> ")
				nid = raw_input("nodeid (key)> ")
				(host, port, nid) = _default_oldvals((host, port, nid),
						(ohost, oport, onid))
				print "nid = '%s'" % nid
				command = 'sendkFindNode("%s", %s, %s)'\
						% (host, port, long(nid, 16))
				exec('d = client.%s' % command)
				exec('d.addCallback(r_getkfindnode)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'kstore':
				host = raw_input("host> ")
				port = raw_input("port> ")
				nid = raw_input("nodeid (key)> ")
				val = raw_input("value> ")
				(host, port, nid, val)\
						= _default_oldvals((host, port, nid, val),\
						(ohost, oport, onid, oval))
				print "nid = '%s'" % nid
				print "val = '%s'" % val
				command = 'sendkStore("%s", %s, %s, "%s")'\
						% (host, port, long(nid, 16), val)
				exec('d = client.%s' % command)
				exec('d.addCallback(r_getkstore)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'kfindvalue':
				host = raw_input("host> ")
				port = raw_input("port> ")
				nid = raw_input("nodeid (key)> ")
				(host, port, nid) = _default_oldvals((host, port, nid),\
						(ohost, oport, onid))
				print "nid = '%s'" % nid
				command = 'sendkFindValue("%s", %s, %s)'\
						% (host, port, long(nid, 16))
				exec('d = client.%s' % command)
				exec('d.addCallback(r_getkfindvalue)')
				exec('d.addErrback(errhdlr, command)')
			elif command == 'knownnodes':
				print "known nodes = %s" % node.config.routing.knownNodes()
			elif command == 'exit':
				done = True
			elif command == '':
				pass
			else:
				print "possible commands: getid, challenge, group, store,"
				print "   retrieve, verify, kfindnode, kfindvalue, kstore,"
				print "   help, knownnodes, exit"
		except ValueError, err:
			print "Error in input: %s\n%s\n%s" % sys.exc_info()
			


if __name__ == '__main__':
	import doctest
	doctest.testmod()
