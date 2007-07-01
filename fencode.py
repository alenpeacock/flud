import base64

"""
fencode.py (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL), version 2.

Provides efficient urlsafe base64 encoding of python types (int, long, string, None, dict, tuple, list) -- in the same vein as BitTorrent's bencode or MNet's mencode.
"""

def fencode(d, lenField=False):
	"""
	Takes string data or a number and encodes it to an efficient URL-friendly
	format.

	>>> n = None
	>>> i = 123455566
	>>> I = 1233433243434343434343434343434343509669586958695869L
	>>> s = "hello there, everyone"
	>>> s2 = "long text ............................................................................... AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
	>>> d = {'a': 'adfasdfasd', 'aaa': 'rrreeeettt', 'f': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}
	>>> d2 = {'a': 123, 'b': 'xyz'}
	>>> d3 = {'a': 123, 'b': 'xyz', 'c': {'x': 456, 'y': 'abc'}}
	>>> d3 = {'a': 123, 'b': 'xyz', 'c': d}
	>>> d4 = {}
	>>> l = [1,2,3,4,'a','b','cde']
	>>> l2 = [i,I,s,d]
	>>> l3 = []
	>>> l4 = [n]
	>>> t = (1,2,3,4,'a','b','cde')
	>>> t2 = (i,I,s,d)
	>>> t3 = ()
	>>> d5 = {t: s, 'n': n, 'a': i, i: "a", 'd': d3, s2: s2}
	>>> l5 = [1,[],2,[],(),{},3,{t: s, 'n': ()}]
	>>> fdecode(fencode(n)) == n
	True
	>>> fdecode(fencode(i)) == i
	True
	>>> fdecode(fencode(I)) == I
	True
	>>> fdecode(fencode(-i)) == -i
	True
	>>> fdecode(fencode(-I)) == -I
	True
	>>> fdecode(fencode(s)) == s
	True
	>>> fdecode(fencode(d)) == d
	True
	>>> fdecode(fencode(d2)) == d2
	True
	>>> fdecode(fencode(d3)) == d3
	True
	>>> fdecode(fencode(d4)) == d4
	True
	>>> fdecode(fencode(l)) == l
	True
	>>> fdecode(fencode(l2)) == l2
	True
	>>> fdecode(fencode(l3)) == l3
	True
	>>> fdecode(fencode(l4)) == l4
	True
	>>> fdecode(fencode(t)) == t
	True
	>>> fdecode(fencode(t2)) == t2
	True
	>>> fdecode(fencode(t3)) == t3
	True
	>>> fdecode(fencode(d5)) == d5
	True
	>>> fdecode(fencode(l5)) == l5
	True
	"""

	def makeLen(i):
		"""
		Returns the integer i as a three-byte length value.

		>>> makeLen(255)
		'\\x00\\xff'
		>>> makeLen(65535)
		'\\xff\\xff'
		"""
		if i > 65535 or i < 0:
			raise ValueError("illegal length for fencoded data"
					"(0 < x <= 65535)")
		return fencode(i)[1:-1]
	
	if isinstance(d, int) or isinstance(d, long):
		val = "%x" % d
		neg = False
		c = 'i'
		if isinstance(d, long):
			c = 'o'
		if d < 0:
			neg = True
			val = val[1:]
			c = c.upper()
		if len(val) % 2 != 0:
			val = "0%s" % val
		val = val.decode('hex')
		if len(val) % 2 != 0:
			val = '\x00' + val
		val = base64.urlsafe_b64encode(val) 
		if lenField:
			if len(val) > 65535:
				raise ValueError("value to large for encode")
			return c+makeLen(len(val))+val
		else:
			return c+val
	elif isinstance(d, str):
		# String data may contain characters outside the allowed charset.
		# urlsafe b64encoding ensures that data can be used inside http urls
		# (and other plaintext representations).
		val = base64.urlsafe_b64encode(d)
		if lenField:
			if len(val) > 65535:
				raise ValueError("value to large for encode")
			return 's'+makeLen(len(val))+val
		else:
			return 's'+val
	elif isinstance(d, dict):
		result = "d"
		contents = ""
		for i in d:
			contents = contents + fencode(i,True) + fencode(d[i],True)
		if lenField:
			result = result+makeLen(len(contents))+contents
		else:
			result = result+contents
		return result
	elif isinstance(d, list):
		result = "l"
		contents = ""
		for i in d:
			contents = contents + fencode(i,True)
		if lenField:
			result = result+makeLen(len(contents))+contents
		else:
			result = result+contents
		return result
	elif isinstance(d, tuple):
		result = "t"
		contents = ""
		for i in d:
			contents = contents + fencode(i,True)
		if lenField:
			result = result+makeLen(len(contents))+contents
		else:
			result = result+contents
		return result
	elif d == None:
		if lenField:
			return 'n'+makeLen(1)+'0'
		else:
			return 'n0'
	else:
		raise ValueError("invalid value passed to fencode: %s" % type(d))
	
def fdecode(d, lenField=False):
	"""
	Takes previously fencoded data and decodes it into its python type(s). 
	"""

	def getLen(s):
		if len(s) != 3 or not isinstance(s, str):
			raise ValueError("fdecode length strings must be 3 bytes long: '%s'"
					% s)
		return fdecode('i'+s+'=')

	def scanval(valstring, lenField=False):
		"""
		scans the given valstring and returns a value and the offset where that
		value ended (as a tuple).  If valstring contains more than one value,
		only the length of the first is returned.  Otherwise, the entire length
		is returned.
		"""
		type = valstring[0]
		if lenField:
			start = 4
			end = start+getLen(valstring[1:4])
		else:
			start = 1
			end = len(valstring)-1
		#print " scanval calling fdecode on val[%d:%d]=%s" % (0, end, valstring)
		return (fdecode(valstring[0:end], True), end)

	if not isinstance(d, str):
		raise ValueError("decode takes string data only")
	type = d[0]
	if lenField:
		length = getLen(d[1:4])
		val = d[4:]
	else:
		val = d[1:len(d)]
	if type == 'i':
		val = base64.urlsafe_b64decode(val)
		val = val.encode('hex')
		return int(val, 16)
	elif type == 'I':
		val = base64.urlsafe_b64decode(val)
		val = val.encode('hex')
		return -int(val, 16)
	elif type == 'o':
		val = base64.urlsafe_b64decode(val)
		val = val.encode('hex')
		return long(val, 16)
	elif type == 'O':
		val = base64.urlsafe_b64decode(val)
		val = val.encode('hex')
		return -long(val, 16)
	elif type == 's':
		return base64.urlsafe_b64decode(val)
	elif type == 'd':
		result = {}
		while len(val) != 0:
			#print "string is: %s (len=%d)" % (val, len(val))
			(key,l1) = scanval(val, True)
			#print "got key '%s' of length %d" % (key,l1)
			(value,l2) = scanval(val[l1:len(val)], True)
			#print "got value '%s' of length %d" % (value,l2)
			result[key] = value
			val = val[l1+l2:]
		return result
	elif type == 'l':
		result = []
		if lenField:
			pass
		while len(val) != 0:
			(v,l) = scanval(val, True)
			result.append(v)
			val = val[l:]
		return result
	elif type == 't':
		result = []
		if lenField:
			pass
		while len(val) != 0:
			(v,l) = scanval(val, True)
			result.append(v)
			val = val[l:]
		return tuple(result)
	elif type == 'n':
		return None
	else:
		raise ValueError("invalid value passed to fdecode"
				" -- cannot fdecode data that wasn't previously fencoded")

if __name__ == '__main__':
	import doctest
	doctest.testmod()

