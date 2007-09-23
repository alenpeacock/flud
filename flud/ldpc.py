import sys
from FludFileCoder import Coder, Decoder

def encode(n,m,fname,stem):
	coder = Coder(n,m,7)
	coder.codeData(fname,stem)

def decode(n,m,dfname,ifnames):
	decoder = Decoder(dfname, n, m, 7)
	for f in ifnames:
		if decoder.decodeData(f):
			break

# note: super primitive commandline args; this is a throwaway:
# ldpc [-d|-e] n m fname stem
n = int(sys.argv[2])
m = int(sys.argv[3])
fname = sys.argv[4]
stem = sys.argv[5]
if sys.argv[1] == '-e':
	encode(n,m,fname,stem)
elif sys.argv[1] == '-d':
	decode(n,m,fname,["%s-%04d" % (stem, i) for i in range(n+m)])
