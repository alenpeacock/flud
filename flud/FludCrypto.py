"""
FludCrypto.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

Provides FludRSA (an enhanced RSA.RSAobj), as well as convenience functions
for creating hashes, finding hash collisions, etc.
"""

import binascii
import operator
import struct
import time
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA, pubkey
from Crypto.Util.randpool import RandomPool

class FludRSA(RSA.RSAobj):
	"""
	Subclasses the Crypto.PublicKey.RSAobj object to add access to the
	privatekey as well as methods for exporting and importing an RSA obj.
	"""
	rand = RandomPool()

	def __init__(self, rsa):
		self.__setstate__(rsa.__getstate__())

	def publickey(self):
		return FludRSA(RSA.construct((self.n, self.e)))

	def privatekey(self):
		return FludRSA(RSA.construct((self.n, self.e, self.d)))

	def encrypt(self, message):
		return RSA.RSAobj.encrypt(self, message, "")

	def exportPublicKey(self):
		return self.publickey().__getstate__()

	def exportPrivateKey(self):
		return self.privatekey().__getstate__()
	
	def id(self):
		"""
		returns the hashstring of the public key
		"""
		#return hashstring(str(self.exportPublicKey()))
		return hashstring(str(self.exportPublicKey()['n']))

	def importPublicKey(key):
		"""
		Can take, as key, a dict describing the public key ('e' and 'n'), a
		string describing n, or a long describing n (in the latter two cases, e
		is assumed to be 65537L).
		"""
		if isinstance(key, str):
			key = long(key, 16)
			key = {'e': 65537L, 'n': key}
		elif isinstance(key, long):
			key = {'e': 65537L, 'n': key}

		if isinstance(key, dict):
			state = key
			pkey = RSA.construct((0L,0L))
			pkey.__setstate__(state)
			return FludRSA(pkey)
		else:
			raise TypeError("type %s not supported by importPublicKey():"\
					" try dict with keys of 'e' and 'n', string representing"\
					" 'n', or long representing 'n'." % type(key))
	importPublicKey = staticmethod(importPublicKey)

	def importPrivateKey(key):
		state = key
		pkey = RSA.construct((0L,0L,0L))
		pkey.__setstate__(state)
		return FludRSA(pkey)
	importPrivateKey = staticmethod(importPrivateKey)

	def generate(keylength):
		return FludRSA(RSA.generate(keylength, FludRSA.rand.get_bytes))
	generate = staticmethod(generate)


def generateKeys(len=1024):
	fludkey = FludRSA.generate(len)
	return fludkey.publickey(), fludkey.privatekey()

def hashstring(string):
	sha256 = SHA256.new()
	sha256.update(string)
	return sha256.hexdigest()

def hashfile(filename):
	sha256 = SHA256.new()
	f = open(filename, "r")
	while 1:
		buf = f.read(1048576) # XXX: 1Mb - magic number
		if buf == "":
			break
		sha256.update(buf)
	f.close()
	return sha256.hexdigest()

def hashstream(file, len):
	sha256 = SHA256.new()
	readsize = 1048576 # XXX: 1Mb - magic number
	while len > 0:
		if len < readsize:
			readsize = len
		buf = file.read(readsize)
		if buf == "":
			break
		sha256.update(buf)
		len = len - readsize
	return sha256.hexdigest()

def generateRandom(n):
	rand = RandomPool()  # using seperate instance of RandomPool purposely
	return rand.get_bytes(n)


def hashcash(match, len, timestamp=False):
	""" trys to find a hash collision of len significant bits.  Returns
	the 256-bit string that produced the collision.  Uses sha256, so match
	should be a sha256 hashstring (as a hexstring), and len should be between
	0 and 256 (lengths close to 256 are intractable).  The timestamp field
	determines whether the current timestamp should be inserted into the
	pre-hash result (to stem sybil attacks targetting specific IDs).
	The result is hex-encoded, so to arrive at the matching hashvalue, you
	would hashstring(binascii.unhexlify(result)).
	"""
	matchint = long(match,16)
	len = 2**(256-len)
	if date:
		gtime = struct.pack("I",int(time.time()))
	while True:
		attempt = generateRandom(32) # 32 random bytes = 256 random bits
		if date:
			# rewrite the 2 lsBs of attempt with the 2 msBs of gtime (time
			# granularity is thus 65536 seconds, or just over 18 hours between
			# intervals -- more than enough for a refresh monthly, weekly, or
			# even daily value)
			attempt = attempt[0:30]+gtime[2:4]
		attempthash = hashstring(attempt)
		attemptint = long(attempthash,16)
		distance = operator.xor(matchint, attemptint)
		if distance < len:
			break
	return binascii.hexlify(attempt)

# XXX: should move all testing to doctest
if __name__ == '__main__':
	fludkey = FludRSA.generate(1024)
	print "fludkey (pub) is: "+str(fludkey.exportPublicKey())
	print "fludkey (priv) is: "+str(fludkey.exportPrivateKey())
	print ""
	pubkeystring = fludkey.exportPublicKey()
	pubkeylongn = pubkeystring['n']
	pubkeystringn = hex(pubkeystring['n'])
	privkeystring = fludkey.exportPrivateKey()
	fludkeyPub = FludRSA.importPublicKey(pubkeystring)
	print "fludkeyPub is: "+str(fludkeyPub.exportPublicKey())
	fludkeyPub2 = FludRSA.importPublicKey(pubkeystringn)
	print "fludkeyPub2 is: "+str(fludkeyPub2.exportPublicKey())
	fludkeyPub3 = FludRSA.importPublicKey(pubkeylongn)
	print "fludkeyPub3 is: "+str(fludkeyPub3.exportPublicKey())
	fludkeyPriv = FludRSA.importPrivateKey(privkeystring)
	print "fludkeyPriv is: "+str(fludkeyPriv.exportPrivateKey())
	plaintext = "test message"
	print "plaintext is: "+plaintext
	ciphertext = fludkeyPub.encrypt(plaintext)
	print "ciphertext is: "+str(ciphertext)
	plaintext2 = fludkeyPriv.decrypt(ciphertext)
	print "decrypted plaintext is: "+plaintext2
	randstring = str(generateRandom(80))
	print "80 bytes of random data: '"+binascii.hexlify(randstring)


	data1='\x00\x1e4%`K\xef\xf6\xdd\x8a\x0eUP\x7f\xb0G\x1d\xb9\xe4\x82\x11n\n\xff\x1a\xc9\x013\xe9\x8e\x99\xb0]M@y\x86l\xb3l'
	edata1=fludkeyPub.encrypt(data1)[0]
	data2=fludkeyPriv.decrypt(edata1)
	print binascii.hexlify(data1)
	print binascii.hexlify(data2)
	print data1 == data2
