import zfec
import zfec.easyfec as easyfec
import zfec.filefec as filefec
from util import fileutil
from util.mathutil import log_ceil

import array, os, re, struct, traceback

FORMAT_FORMAT = "%%s.%%0%dd_%%0%dd%%s"
RE_FORMAT = "%s.[0-9]+_[0-9]+%s"
def encode_to_files(inf, fsize, dirname, prefix, k, m, suffix=".fec", overwrite=False, verbose=False):
	"""
	Encode inf, writing the shares to specially named, newly created files.

	@param fsize: calling read() on inf must yield fsize bytes of data and 
		then raise an EOFError
	@param dirname: the name of the directory into which the sharefiles will
		be written
	"""
	mlen = len(str(m))
	format = FORMAT_FORMAT % (mlen, mlen,)

	padbytes = zfec.util.mathutil.pad_size(fsize, k)

	fns = []
	fs = []
	try:
		for shnum in range(m):
			hdr = filefec._build_header(m, k, padbytes, shnum)

			fn = os.path.join(dirname, format % (prefix, shnum, m, suffix,))
			if verbose:
				print "Creating share file %r..." % (fn,)
			if overwrite:
				f = open(fn, "wb")
			else:
				flags = os.O_WRONLY|os.O_CREAT|os.O_EXCL | (hasattr(os, 
						'O_BINARY') and os.O_BINARY)
				fd = os.open(fn, flags)
				f = os.fdopen(fd, "wb")
			f.write(hdr)
			fs.append(f)
			fns.append(fn)
		sumlen = [0]
		def cb(blocks, length):
			assert len(blocks) == len(fs)
			oldsumlen = sumlen[0]
			sumlen[0] += length
			if verbose:
				if int((float(oldsumlen) / fsize) * 10) \
						!= int((float(sumlen[0]) / fsize) * 10):
					print str(int((float(sumlen[0]) / fsize) * 10) * 10) \
							+ "% ...",
			
			if sumlen[0] > fsize:
				raise IOError("Wrong file size -- possibly the size of the"
						" file changed during encoding.  Original size: %d,"
						" observed size at least: %s" % (fsize, sumlen[0],))
			for i in range(len(blocks)):
				data = blocks[i]
				fs[i].write(data)
				length -= len(data)

		filefec.encode_file_stringy_easyfec(inf, cb, k, m, chunksize=4096)
	except EnvironmentError, le:
		print "Cannot complete because of exception: "
		print le
		print "Cleaning up..."
		# clean up
		while fs:
			f = fs.pop()
			f.close() ; del f
			fn = fns.pop()
			if verbose:
				print "Cleaning up: trying to remove %r..." % (fn,)
			fileutil.remove_if_possible(fn)
		return None
	if verbose:
		print 
		print "Done!"
	return fns

# Note: if you really prefer base-2 and you change this code, then please
# denote 2^20 as "MiB" instead of "MB" in order to avoid ambiguity.
# Thanks.
# http://en.wikipedia.org/wiki/Megabyte
MILLION_BYTES=10**6

def decode_from_files(outf, infiles, verbose=False):
	"""
	Decode from the first k files in infiles, writing the results to outf.
	"""
	assert len(infiles) >= 2
	infs = []
	shnums = []
	m = None
	k = None
	padlen = None

	byteswritten = 0
	for f in infiles:
		(nm, nk, npadlen, shnum,) = filefec._parse_header(f)
		if not (m is None or m == nm):
			raise CorruptedShareFilesError("Share files were corrupted --"
					" share file %r said that m was %s but another share file"
					" previously said that m was %s" % (f.name, nm, m,))
		m = nm
		if not (k is None or k == nk):
			raise CorruptedShareFilesError("Share files were corrupted --"
					" share file %r said that k was %s but another share file"
					" previously said that k was %s" % (f.name, nk, k,))
		if k > len(infiles):
			raise InsufficientShareFilesError(k, len(infiles))
		k = nk
		if not (padlen is None or padlen == npadlen):
			raise CorruptedShareFilesError("Share files were corrupted --"
					" share file %r said that pad length was %s but another"
					" share file previously said that pad length was %s" 
					% (f.name, npadlen, padlen,))
		padlen = npadlen

		infs.append(f)
		shnums.append(shnum)

		if len(infs) == k:
			break

	dec = easyfec.Decoder(k, m)

	while True:
		chunks = [ inf.read(filefec.CHUNKSIZE) for inf in infs ]
		if [ch for ch in chunks if len(ch) != len(chunks[-1])]:
			raise CorruptedShareFilesError("Share files were corrupted --"
					" all share files are required to be the same length,"
					" but they weren't.")

		if len(chunks[-1]) == filefec.CHUNKSIZE:
			# Then this was a full read, so we're still in the sharefiles.
			resultdata = dec.decode(chunks, shnums, padlen=0)
			outf.write(resultdata)
			byteswritten += len(resultdata)
			if verbose:
				if ((byteswritten - len(resultdata)) / (10*MILLION_BYTES)) \
						!= (byteswritten / (10*MILLION_BYTES)):
					print str(byteswritten / MILLION_BYTES) + " MB ...",
		else:
			# Then this was a short read, so we've reached the end of the
			# sharefiles.
			resultdata = dec.decode(chunks, shnums, padlen)
			outf.write(resultdata)
			return True
	if verbose:
		print
		print "Done!"
	return True


# fludfilefec -- modified zfec filefec for use with flud, based on:
#
# zfec -- fast forward error correction library with Python interface
# 
# Copyright (C) 2007 Allmydata, Inc.
# Author: Zooko Wilcox-O'Hearn
# 
# This file is part of zfec.
# 
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version, with the added permission that, if you become obligated
# to release a derived work under this licence (as per section 2.b), you may
# delay the fulfillment of this obligation for up to 12 months.  See the file
# COPYING for details.
#
# If you would like to inquire about a commercial relationship with Allmydata,
# Inc., please contact partnerships@allmydata.com and visit
# http://allmydata.com/.
