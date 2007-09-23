#include "Coder.h"
#include "CodingException.h"
#include <iostream>

const int Coder::headerSz = CodedBlocks::headerSz;

Coder::Coder(int dataBlocks, int parityBlocks, int leftDegree) {
	this->dataBlocks = dataBlocks;
	this->parityBlocks = parityBlocks;
	this->leftDegree = leftDegree;
	sessionType = TypeSTAIRS;
	fecSession.SetVerbosity(0);
	seed = 21;
}

CodedBlocks Coder::codeData(char* data, int length) {
	return codeData(data, length, dataBlocks, parityBlocks);
}

CodedBlocks Coder::codeData(char* data, int length, 
		int dataBlocks, int parityBlocks) {
	blockSize = (int)ceil((double)length / (double)dataBlocks);
	int totalBlocks = dataBlocks+parityBlocks;
	// blockSize must be a multiple of 4
	int blockPad = (blockSize%4 == 0) ? 0 : 4-(blockSize%4);  
	blockSize += blockPad;  
	int filePad = (blockSize * dataBlocks) - length;
	if (fecSession.InitSession(dataBlocks, parityBlocks, blockSize, FLAG_CODER, 
				leftDegree, seed, sessionType) == LDPC_ERROR) {
		std::cerr << "Coder: unable to initialize LDPC session\n";
		throw CodingException("unable to initialize LDPC session");
	}
	// allocate blocks
	char** blockArray = NULL;
	blockArray = (char**)calloc(totalBlocks, sizeof(char*));
	char** fecArray = NULL;
	fecArray = (char**)calloc(totalBlocks, sizeof(char*));
	// XXX: fecArray and blockArray are redundant -- only needed because
	//      BuildFecPacket() needs access to the array without header info in
	//      it.  This should be fixed by getting rid of blockArray and modifying
	//      CodedBlock class to contain seqno and filepad members.  Coders 
	//      (fileCoder, testCoder, etc.) would also need to change to write
	//      this header out.  Decoders (fileDecoder, testCoder) would also need
	//      to make this change.
	if (blockArray == NULL || fecArray == NULL) {
		std::cerr << "Coder: insufficient memory at line " << __LINE__ << "\n";
		throw CodingException("insufficient memory");
	}
	// Copy data into dataBlocks 
	for (int i=0; i<dataBlocks; i++) {
		blockArray[i] = (char*)calloc(blockSize+headerSz, sizeof(char));
		fecArray[i] = (char*)calloc(blockSize, sizeof(char));
		*((int*)blockArray[i]) = htonl(i);  // seqno
		*((int*)blockArray[i]+1) = htonl(filePad); // filePad
		if (blockSize*i + blockSize > length) {
			// deal with last odd bit of input data by padding with 0s
			int sz = 0;
			int padsz = blockSize;
			if (blockSize*i < length) {
				// handles the case where there are sz bytes left to stick
				// into this block, and padsz to fill with zeros.  Otherwise,
				// fill the whole block with 0s.
				sz = length % blockSize;
				padsz = blockSize - sz;
			}
			memcpy(blockArray[i]+headerSz, data+(blockSize*i), sz);
			memcpy(fecArray[i], data+(blockSize*i), sz);
			memset(blockArray[i]+headerSz+sz, 0, padsz);
			memset(fecArray[i]+sz, 0, padsz);
		} else {
			memcpy(blockArray[i]+headerSz, data+(blockSize*i), blockSize);
			memcpy(fecArray[i], data+(blockSize*i), blockSize);
		}
	}
	// Create parity 
	for (int i=0; i<parityBlocks; i++) {
		blockArray[i+dataBlocks] = (char*)calloc(blockSize+headerSz, sizeof(char));
		fecArray[i+dataBlocks] = (char*)calloc(blockSize, sizeof(char));
		if (blockArray[i+dataBlocks] == NULL || fecArray[i+dataBlocks] == NULL) {
			std::cerr << "Coder: insufficient memory at line " << __LINE__ << "\n";
			throw CodingException("insufficient memory");
		}
		*((int*)blockArray[i+dataBlocks]) = htonl(i+dataBlocks); // seqno
		*((int*)blockArray[i+dataBlocks]+1) = htonl(filePad); // filePad
		fecSession.BuildFecPacket((void**)fecArray, i, fecArray[i+dataBlocks]);
		memcpy(blockArray[i+dataBlocks]+headerSz, fecArray[i+dataBlocks],
				blockSize);
	}

	return CodedBlocks(blockArray, blockSize+headerSz, totalBlocks);
}

int Coder::getBlockSize() {
	return blockSize;
}
