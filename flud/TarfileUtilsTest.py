#!/usr/bin/python

import gzip
from Crypto.Hash import SHA256
import tarfile, tempfile, random, os

from flud.fencode import fencode
import flud.TarfileUtils

def maketarball(numfiles, avgsize, hashnames=False, addmetas=False):
	tarballname = tempfile.mktemp()+".tar"
	tarball = tarfile.open(tarballname, 'w')
	if addmetas:
		metafname = tempfile.mktemp()
		metaf = file(metafname, 'w')
		metaf.write('m'*48)
		metaf.close()
	for i in xrange(numfiles):
		fname = tempfile.mktemp()
		f = file(fname, 'wb')
		size = int(avgsize * (random.random()+0.5))
		blocksize = 65*1024
		if hashnames:
			sha256 = SHA256.new()
		for j in range(0, size, blocksize):
			if j+blocksize > size:
				block = 'a'*(size-j)
			else:
				block = 'a'*blocksize
			if hashnames:
				sha256.update(block)
			f.write(block)
		f.close()
		arcname = fname
		if hashnames:
			arcname = fencode(int(sha256.hexdigest(),16))
		tarball.add(fname, arcname)
		if addmetas:
			tarball.add(metafname, arcname+".343434.meta")
		os.remove(fname)
	if addmetas:
		os.remove(metafname)
	contents = tarball.getnames()
	tarball.close()
	return tarballname, contents

def gzipTarball(tarball):
	f = gzip.GzipFile(tarball+".gz", 'wb')
	f.write(file(tarball, 'rb').read())
	f.close()
	os.remove(tarball)
	return tarball+".gz"

def main():

	# test plain TarfileUtils.delete()
	(tballname, contents) = maketarball(5, 4096)
	TarfileUtils.delete(tballname, contents[2:4])
	tarball = tarfile.open(tballname, 'r')
	os.remove(tballname)
	assert(tarball.getnames() == contents[:2]+contents[4:])	
	tarball.close()

	# test gzip TarfileUtils.delete()
	(tballname, contents) = maketarball(5, 4096)
	tballname = gzipTarball(tballname)
	TarfileUtils.delete(tballname, contents[2:4])
	tarball = tarfile.open(tballname, 'r')
	os.remove(tballname)
	assert(tarball.getnames() == contents[:2]+contents[4:])	
	tarball.close()

	# test plain TarfileUtils.concatenate()
	(tballname1, contents1) = maketarball(5, 4096)
	(tballname2, contents2) = maketarball(5, 4096)
	TarfileUtils.concatenate(tballname1, tballname2)
	assert(not os.path.exists(tballname2))
	tarball = tarfile.open(tballname1, 'r')
	os.remove(tballname1)
	assert(tarball.getnames() == contents1+contents2)

	# test TarfileUtils.concatenate(gz, plain)
	(tballname1, contents1) = maketarball(5, 4096)
	(tballname2, contents2) = maketarball(5, 4096)
	tballname1 = gzipTarball(tballname1)
	TarfileUtils.concatenate(tballname1, tballname2)
	assert(not os.path.exists(tballname2))
	tarball = tarfile.open(tballname1, 'r')
	os.remove(tballname1)
	assert(tarball.getnames() == contents1+contents2)

	# test TarfileUtils.concatenate(plain, gz)
	(tballname1, contents1) = maketarball(5, 4096)
	(tballname2, contents2) = maketarball(5, 4096)
	tballname2 = gzipTarball(tballname2)
	TarfileUtils.concatenate(tballname1, tballname2)
	assert(not os.path.exists(tballname2))
	tarball = tarfile.open(tballname1, 'r')
	os.remove(tballname1)
	assert(tarball.getnames() == contents1+contents2)

	# test TarfileUtils.concatenate(gz, gz)
	(tballname1, contents1) = maketarball(5, 4096)
	(tballname2, contents2) = maketarball(5, 4096)
	tballname1 = gzipTarball(tballname1)
	tballname2 = gzipTarball(tballname2)
	TarfileUtils.concatenate(tballname1, tballname2)
	assert(not os.path.exists(tballname2))
	tarball = tarfile.open(tballname1, 'r')
	os.remove(tballname1)
	assert(tarball.getnames() == contents1+contents2)

	# test TarfileUtils.verifyHashes(plain no meta)
	(tballname, contents) = maketarball(5, 4096, True)
	assert(TarfileUtils.verifyHashes(tballname, contents[2:4]))
	os.remove(tballname)

	# test TarfileUtils.verifyHashes(plain with meta)
	(tballname, contents) = maketarball(5, 4096, True, True)
	assert(TarfileUtils.verifyHashes(tballname, contents[2:4]), ".meta")
	os.remove(tballname)

	# test TarfileUtils.verifyHashes(gzipped no meta)
	(tballname, contents) = maketarball(5, 4096, True)
	tballname = gzipTarball(tballname)
	assert(TarfileUtils.verifyHashes(tballname, contents[2:4]))
	os.remove(tballname)

	# test TarfileUtils.verifyHashes(gzipped with meta)
	(tballname, contents) = maketarball(5, 4096, True, True)
	tballname = gzipTarball(tballname)
	assert(TarfileUtils.verifyHashes(tballname, contents[2:4]), ".meta")
	os.remove(tballname)

if __name__ == "__main__":
	main()
