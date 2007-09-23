#!/usr/bin/python

import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(
	os.path.abspath(__file__)))))
from flud.FludFileCoder import Coder, Decoder

if __name__ == '__main__':
	if len(sys.argv) != 2:
		print "usage: %s sourcefile" % sys.argv[0]
	else:
		fname = sys.argv[1]
		stem = fname+"_seg-"
		stem2 = fname+"_seg2-"
		c = Coder(20, 20, 7)
		stemfiles = c.codeData(sys.argv[1],stem)
		print "encoded %s to:" % fname
		print stemfiles

		d = Decoder(fname+"-recovered", 20, 20, 7)
		for f in stemfiles:
			print "decoding %s" % f
			ret = d.decodeData(f)
			if not ret == 0:
				break

		print "decoded files"
		
