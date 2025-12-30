"""
FludCrypto.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

Provides FludRSA (a thin wrapper around Cryptodome.PublicKey.RSA.RsaKey), as
well as convenience functions for creating hashes, finding hash collisions,
etc.
"""

import binascii
import operator
import struct
import time
from Cryptodome.Cipher import PKCS1_v1_5
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA
from Cryptodome.Random import atfork, get_random_bytes
from Cryptodome.Util.number import inverse

class FludRSA(object):
    """
    Lightweight wrapper around Cryptodome.PublicKey.RSA.RsaKey that keeps the
    legacy FludRSA interface without subclassing private PyCrypto internals.
    """

    def __init__(self, rsa):
        if isinstance(rsa, FludRSA):
            rsa = rsa._key
        if not isinstance(rsa, RSA.RsaKey):
            raise TypeError("FludRSA requires an RSA.RsaKey, got %s" % type(rsa))
        self._key = rsa

    def __getattr__(self, name):
        # Delegate to the underlying RsaKey for attributes like n, e, d, etc.
        return getattr(self._key, name)

    def __getstate__(self):
        """
        Return a dict representation compatible with older PyCrypto
        __getstate__ output, so stored configs still round-trip.
        """
        state = {'n': self._key.n, 'e': self._key.e}
        if self._key.has_private():
            state['d'] = self._key.d
            if getattr(self._key, 'p', None) and getattr(self._key, 'q', None):
                p = self._key.p
                q = self._key.q
                state.update({
                    'p': p,
                    'q': q,
                    'u': inverse(q, p),
                    'exp1': self._key.d % (p - 1),
                    'exp2': self._key.d % (q - 1),
                })
        return state

    def publickey(self):
        return FludRSA(self._key.publickey())

    def privatekey(self):
        if not self._key.has_private():
            raise ValueError("public key does not include a private exponent")
        return FludRSA(RSA.construct(
            (self._key.n, self._key.e, self._key.d),
            consistency_check=False))

    def encrypt(self, message):
        if isinstance(message, str):
            message = message.encode()
        cipher = PKCS1_v1_5.new(self._key)
        # Keep compatibility with the old PyCrypto interface that returned
        # a 1-tuple.
        return (cipher.encrypt(message),)

    def decrypt(self, ciphertext):
        if isinstance(ciphertext, tuple):
            ciphertext = ciphertext[0]
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode()
        cipher = PKCS1_v1_5.new(self._key)
        plaintext = cipher.decrypt(ciphertext, None)
        if plaintext is None:
            raise ValueError("failed to decrypt ciphertext")
        return plaintext

    def exportPublicKey(self):
        return self.publickey().__getstate__()

    def exportPrivateKey(self):
        return self.privatekey().__getstate__()
    
    def id(self):
        """
        returns the hashstring of the public key
        """
        return hashstring(str(self.exportPublicKey()['n']))

    def importPublicKey(key):
        """
        Can take, as key, a dict describing the public key ('e' and 'n'), a
        string describing n, or a long describing n (in the latter two cases, e
        is assumed to be 65537L).
        """
        if isinstance(key, str):
            key = int(key, 16)
            key = {'e': 65537, 'n': key}
        elif isinstance(key, int):
            key = {'e': 65537, 'n': key}

        if isinstance(key, dict):
            n = key['n']
            e = key.get('e', 65537)
            pkey = RSA.construct((n, e))
            return FludRSA(pkey)
        else:
            raise TypeError("type %s not supported by importPublicKey():"\
                    " try dict with keys of 'e' and 'n', string representing"\
                    " 'n', or long representing 'n'." % type(key))
    importPublicKey = staticmethod(importPublicKey)

    def importPrivateKey(key):
        if not isinstance(key, dict):
            raise TypeError("importPrivateKey expects a dict with RSA values")
        n = key['n']
        e = key.get('e', 65537)
        d = key['d']
        p = key.get('p')
        q = key.get('q')
        if p and q:
            pkey = RSA.construct((n, e, d, p, q), consistency_check=False)
        else:
            pkey = RSA.construct((n, e, d), consistency_check=False)
        return FludRSA(pkey)
    importPrivateKey = staticmethod(importPrivateKey)

    def generate(keylength=2048):
        atfork()
        return FludRSA(RSA.generate(keylength, randfunc=get_random_bytes))
    generate = staticmethod(generate)


def generateKeys(len=2048):
    fludkey = FludRSA.generate(len)
    return fludkey.publickey(), fludkey.privatekey()

def hashstring(string):
    sha256 = SHA256.new()
    if isinstance(string, str):
        string = string.encode()
    sha256.update(string)
    return sha256.hexdigest()

def hashfile(filename):
    sha256 = SHA256.new()
    f = open(filename, "rb")
    while 1:
        buf = f.read(1048576) # XXX: 1Mb - magic number
        if buf == b"":
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
        if buf == b"":
            break
        sha256.update(buf)
        len = len - readsize
    return sha256.hexdigest()

def generateRandom(n):
    atfork()
    return get_random_bytes(n)


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
    matchint = int(match,16)
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
        attemptint = int(attempthash,16)
        distance = operator.xor(matchint, attemptint)
        if distance < len:
            break
    return binascii.hexlify(attempt)

# XXX: should move all testing to doctest
if __name__ == '__main__':
    fludkey = FludRSA.generate(2048)
    print("fludkey (pub) is: "+str(fludkey.exportPublicKey()))
    print("fludkey (priv) is: "+str(fludkey.exportPrivateKey()))
    print("")
    pubkeystring = fludkey.exportPublicKey()
    pubkeylongn = pubkeystring['n']
    pubkeystringn = hex(pubkeystring['n'])
    privkeystring = fludkey.exportPrivateKey()
    fludkeyPub = FludRSA.importPublicKey(pubkeystring)
    print("fludkeyPub is: "+str(fludkeyPub.exportPublicKey()))
    fludkeyPub2 = FludRSA.importPublicKey(pubkeystringn)
    print("fludkeyPub2 is: "+str(fludkeyPub2.exportPublicKey()))
    fludkeyPub3 = FludRSA.importPublicKey(pubkeylongn)
    print("fludkeyPub3 is: "+str(fludkeyPub3.exportPublicKey()))
    fludkeyPriv = FludRSA.importPrivateKey(privkeystring)
    print("fludkeyPriv is: "+str(fludkeyPriv.exportPrivateKey()))
    plaintext = "test message".encode('utf-8')
    print("plaintext is: {plaintext}")
    ciphertext = fludkeyPub.encrypt(plaintext)
    print("ciphertext is: "+str(ciphertext))
    plaintext2 = fludkeyPriv.decrypt(ciphertext)
    print(f"decrypted plaintext is: {plaintext2}")
    assert plaintext2 == plaintext

    randstring = str(generateRandom(80)).encode('utf-8')
    print("80 bytes of random data: {binascii.hexlify(randstring)}")
    data1=randstring

    # leading zeroes get lost, since encryption treats the data as a number
    #data1='\x00\x00\x00\x1e4%`K\xef\xf6\xdd\x8a\x0eUP\x7f\xb0G\x1d\xb9\xe4\x82\x11n\n\xff\x1a\xc9\x013\xe9\x8e\x99\xb0]M@y\x86l\xb3l'

    edata1=fludkeyPub.encrypt(data1)[0]
    data2=fludkeyPriv.decrypt(edata1)
    print(binascii.hexlify(data1))
    print(binascii.hexlify(data2))
    assert data1 == data2
