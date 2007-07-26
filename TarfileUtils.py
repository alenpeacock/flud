import os, stat, sys, tarfile, tempfile
from FludCrypto import hashstream
from fencode import fencode

"""
TarfileUtils.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL).

Provides additional tarfile functionality (deletion of a member from a
tarball, and concatenation of tarballs).
"""

def delete(tarball, membernames):
	"""
	Deletes a member file[s] from a tarball.  Returns the names of deleted
	members if they areremoved, False if the file[s] aren't members.  If
	membernames contains all the members in the tarball, the entire tarball is
	deleted
	"""
	f = tarfile.open(tarball, 'r')
	if not isinstance(membernames, list):
		membernames = [membernames]
	tarnames = f.getnames()
	for membername in membernames: 
		if not membername in tarnames:
			membernames.remove(membername)
	if len(membernames) < 1:
		f.close()
		return False
	if len(tarnames) == len(membernames):
		f.close()
		os.remove(tarball)
		return True
	f.close()
	f = open(tarball, 'r+')
	tfile = tempfile.mktemp()
	f2 = open(tfile, 'w')
	empty = tarfile.BLOCKSIZE * '\0'
	done = False
	removednames = []
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
			if name in membernames:
				f.seek(blocks*tarfile.BLOCKSIZE + f.tell())
				removednames.append(name)
			else:
				f2.write(bytes)
				for i in range(blocks):
					f2.write(f.read(tarfile.BLOCKSIZE))
	f2.close()
	f.close()
	os.rename(tfile, tarball)
	return removednames

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
		header = f.read(tarfile.BLOCKSIZE)
		if header == "":
			print "error: end of archive not found"
			return
		elif header == empty:
			emptyblockcount += 1
			if emptyblockcount == 2:
				done = True
		else:
			emptyblockcount = 0
			fsize = eval(header[124:135])
			skip = int(round(float(fsize) / float(tarfile.BLOCKSIZE) + 0.5))
			f.seek(skip*tarfile.BLOCKSIZE, 1)

	# truncate the file to the spot before the end-of-tar marker 
	trueend = f.tell() - (tarfile.BLOCKSIZE*2)
	f.seek(trueend)
	f.truncate()

	# now write the contents of the second tarfile into this spot
	f2 = open(tarfile2, "r")
	done = False
	while not done:
		header = f2.read(tarfile.BLOCKSIZE)
		if header == "":
			print "error: end of archive not found"
			f.seek(trueend)
			f.write(empty*2)
			return
		else:
			f.write(header)
			if header == empty:
				emptyblockcount += 1
				if emptyblockcount == 2:
					done = True
			else:
				emptyblockcount = 0
				fsize = eval(header[124:135])
				bsize = int(round(float(fsize) / float(tarfile.BLOCKSIZE) 
					+ 0.5))
				# XXX: break this up if large
				data = f2.read(bsize*tarfile.BLOCKSIZE)
				f.write(data)

	f2.close()
	f.close()
	
	# and delete the second tarfile
	os.remove(tarfile2)
	#print "concatenated %s to %s" % (tarfile2, tarfile1)

def verifyHashes(tarball, ignoreExt=None):
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
			if bytes[0] == '\0' and bytes[124] == '\0':
				print "WARNING: read nulls when expecting file header"
				break
			name = bytes[0:99]
			name = name[:name.find(chr(0))]
			size = int(bytes[124:135], 8)
			blocks = size / tarfile.BLOCKSIZE
			if ignoreExt and name[-len(ignoreExt):] == ignoreExt:
				f.seek(size, 1)
			else:
				digest = hashstream(f, size)
				digest = fencode(int(digest,16))
				if name == digest:
					#print "%s == %s" % (name, digest)
					digests.append(name)
				else:
					#print "%s != %s" % (name, digest)
					f.close()
					return []
			if (size % tarfile.BLOCKSIZE) > 0:
				blocks += 1
			f.seek((blocks * tarfile.BLOCKSIZE) - size + f.tell())
	f.close()
	return digests


if __name__ == "__main__":
	if (len(sys.argv) < 4 or sys.argv[1] != "-d") \
			and (len(sys.argv) != 4 or sys.argv[1] != "-c") \
			and sys.argv[1] != "-v":
		print "usage: [-d tarfile tarfilemembers]\n"\
				+"       [-c tarfile1 tarfile2]\n"\
				+"       [-v tarfile]\n"\
				+" -d deletes tarfilemembers from tarfile,\n"\
				+" -c concatenates tarfile1 and tarfile2 into tarfile1\n"\
				+" -v verifies that the names of files in tarfile are sha256\n"
		sys.exit(-1)
	if sys.argv[1] == "-d":
		deleted = delete(sys.argv[2], sys.argv[3:])
		if deleted == sys.argv[3:]:
			print "%s successfully deleted from %s" % (deleted, sys.argv[2])
		else:
			faileddeletes = [x for x in sys.argv[3:] if x not in deleted]
			print "could not delete %s from %s" % (faileddeletes, sys.argv[2])
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
