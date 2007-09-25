"""
FludFileCoder.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

Provides wrapper functionality around ldpc python module, for encoding and
decoding files.
"""

from filecoder import c_Coder, c_Decoder

class Coder:

	def __init__(self, dataBlocks, parityBlocks, leftDegree):
		self.c_coder = c_Coder(dataBlocks, parityBlocks, leftDegree)

	def codeData(self, filename, stem):
		return self.c_coder.codeData(filename, stem)


class Decoder:

	def __init__(self, destFile, dataBlocks, parityBlocks, leftDegree):
		self.c_decoder = c_Decoder(destFile, dataBlocks, parityBlocks, 
				leftDegree)

	def done(self):
		return self.c_decoder.done()

	def decodeData(self, filename):
		return self.c_decoder.decodeData(filename)
