#!/usr/bin/python

"""
mastermetadataViewer.py (c) 2003-2006 Alen Peacock.  This program is
distributed under the terms of the GNU General Public License (the GPL).

Utility for displaying master metadata.
"""

from fencode import fencode, fdecode
from FludCrypto import FludRSA
import sys, os
import ConfigParser

if __name__ == "__main__":
	if len(sys.argv) < 2:
		print "usage: %s <filename> " % sys.argv[0]
		sys.exit()
	else:
		fname = sys.argv[1]
		raw = False
	
	try:
		# try to use Ku to decrypt metadata
		try:
			fludhome = os.environ['FLUDHOME']
		except:
			home = os.environ['HOME']
			fludhome = home+"/.flud"
		fludconfig = fludhome+"/flud.conf"
		c = ConfigParser.ConfigParser()
		if os.path.isfile(fludconfig) == True:
			conffile = file(fludconfig, "r")
			c.readfp(conffile)
		privkey = FludRSA.importPrivateKey( 
				eval(c.get("identification","Kr"))) 
	except:
		privkey = None

	f = os.open(fname, os.O_RDONLY)
	data = os.read(f,1280000)
	os.close(f)
	print "data is '%s'" % data
	data = fdecode(data)
	for i in data:
		if isinstance(data[i],dict):
			print "%s -> %s" % (i, data[i])
	print "--------------------"
	for i in data:
		if not isinstance(data[i],dict):
			print "%s <- %s" % (fencode(data[i]), i)

