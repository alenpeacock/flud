import os, stat, sys, tarfile, tempfile
from FludCrypto import hashstream

"""
TarfileUtils.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL).

Provides additional tarfile functionality (deletion of a member from a
tarball, and concatenation of tarballs).
"""

def delete(tarball, membername):
	"""
	Deletes a member file from a tarball.  Returns True if the file is removed,
	False if the file isn't a member.  If membername is the only file in
	tarball, the entire tarball is deleted
	"""
	f = tarfile.open(tarball, 'r')
	if not membername in f.getnames():
		f.close()
		return False
	if len(f.getnames()) == 1:
		f.close()
		os.remove(tarball)
		return True
	f.close()
	f = open(tarball, 'r+')
	tfile = tempfile.mktemp()
	f2 = open(tfile, 'w')
	empty = tarfile.BLOCKSIZE * '\0'
	done = False
	found = False
	while not done:
		bytes = f.read(tarfile.BLOCKSIZE)
		if bytes == "":
			done = True
		elif bytes == empty:
			f2.write(bytes)
		else:
			name = bytes[0:99]
			name = name[:name.find(chr(0))]
			size = int(bytes[124:135], 8)
			blocks = size / tarfile.BLOCKSIZE
			if (size % tarfile.BLOCKSIZE) > 0:
				blocks += 1
			if name == membername:
				f.seek(blocks*tarfile.BLOCKSIZE + f.tell())
				found = True
			else:
				f2.write(bytes)
				for i in range(blocks):
					f2.write(f.read(tarfile.BLOCKSIZE))
	f2.close()
	f.close()
	os.rename(tfile, tarball)
	return found

def concatenate(tarfile1, tarfile2):
	"""
	Combines tarfile1 and tarfile2 into tarfile1.  tarfile1 is modified in the
	process, and tarfile2 is deleted.
	"""
	f = open(tarfile1, "r+")
	done = False
	e = '\0'
	empty = tarfile.BLOCKSIZE*e
	emptyblockcount = 0
	while not done:
		# read blocks until we encounter 2 blocks in a row that are blank
		# (2 blank blocks is the end-of-tar marker)
		bytes = f.read(tarfile.BLOCKSIZE)
		if bytes == "":
			done = True
		if bytes == empty:
			emptyblockcount += 1
			if emptyblockcount >= 2:
				done = True
		else:
			if emptyblockcount > 0:
				emptyblockcount = 0
	# truncate the file to the spot before the end-of-tar marker 
	falseend = f.tell() - (tarfile.BLOCKSIZE*2)
	f.seek(falseend)
	f.truncate()

	# now write the contents of the second tarfile into this spot
	f2 = open(tarfile2, "r")
	done = False
	while not done:
		bytes = f2.read(tarfile.BLOCKSIZE)
		if bytes == "":
			done = True
		else:
			f.write(bytes)

	f2.close()
	f.close()
	
	# and delete the second tarfile
	os.remove(tarfile2)
	#print "concatenated %s to %s" % (tarfile2, tarfile1)

def verifyHashes(tarball):
	# return all the names of files in this tarball if hash checksum passes,
	# otherwise return False
	digests = []
	done = False
	f = open(tarball, 'r')
	empty = tarfile.BLOCKSIZE * '\0'
	while not done:
		bytes = f.read(tarfile.BLOCKSIZE)
		if bytes == "":
			done = True
		elif bytes == empty:
			pass
		else:
			name = bytes[0:99]
			name = name[:name.find(chr(0))]
			size = int(bytes[124:135], 8)
			blocks = size / tarfile.BLOCKSIZE
			if (size % tarfile.BLOCKSIZE) > 0:
				blocks += 1
			digest = hashstream(f, size)
			if name == digest:
				digests.append(name)
			else:
				f.close()
				return []
			f.seek((blocks * tarfile.BLOCKSIZE) - size + f.tell())
	f.close()
	return digests


if __name__ == "__main__":
	if (len(sys.argv) != 4 or (sys.argv[1] != "-d" and sys.argv[1] != "-c")) \
			and sys.argv[1] != "-v":
		print "usage: [-d tarfile tarfilemember]\n"\
				+"       [-c tarfile1 tarfile2]\n"\
				+"       [-v tarfile]\n"\
				+" -d deletes tarfilemember from tarfile,\n"\
				+" -c concatenates tarfile1 and tarfile2 into tarfile1\n"\
				+" -v verifies that the names of files in tarfile are sha256\n"
		sys.exit(-1)
	if sys.argv[1] == "-d":
		if delete(sys.argv[2], sys.argv[3]):
			print "%s successfully deleted from %s" % (sys.argv[3], sys.argv[2])
		else:
			print "could not delete %s from %s" % (sys.argv[3], sys.argv[2])
	elif sys.argv[1] == "-c":
		concatenate(sys.argv[2], sys.argv[3])
		print "concatenated %s and %s into %s" % (sys.argv[2], sys.argv[3],
				sys.argv[2])
	elif sys.argv[1] == "-v":
		digests = verifyHashes(sys.argv[2])
		if digests:
			print "verified tarfile member digests for: %s" % digests
		else:
			print "some tarfile members failed digest check"
