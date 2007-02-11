#include "Decoder.h"
#include <iostream>


const int Decoder::headerSz = CodedBlocks::headerSz;

Decoder::Decoder(int blockLen, int dataBlocks, int parityBlocks, 
		int leftDegree) {
	this->blockLen = blockLen;
	this->blockSize = blockLen-headerSz;
	this->dataBlocks = dataBlocks;
	this->parityBlocks = parityBlocks;
	this->leftDegree = leftDegree;
	sessionType = TypeSTAIRS;
	fecSession.SetVerbosity(0);
	seed = 21;
	if (fecSession.InitSession(dataBlocks, parityBlocks, blockSize, 
				FLAG_DECODER, leftDegree, seed, sessionType ) == LDPC_ERROR) {
		std::cerr << "Decoder Error: Unable to initialize LDPC Session\n";
	}
	blocksArray = (char**)calloc(dataBlocks, sizeof(char*));
	if (blocksArray == NULL) {
		std::cerr << "Decoder Error: insufficient memory\n";
	}
}

int Decoder::decodeData(char *&data, char* dataBuf, int dataBlocks, 
		int parityBlocks) {
	int seqNo = ntohl(*(int*)dataBuf);
	int filePad = ntohl(*(int*)(dataBuf+4));
	//std::cout << "seqNo=" << seqNo << std::endl;
	fecSession.DecodeFecStep((void**)blocksArray, (dataBuf+headerSz), 
			seqNo);
	if (!fecSession.IsDecodingComplete((void**)blocksArray)) return 0;
	
	data = (char*)calloc((blockSize)*dataBlocks, sizeof(char));
	if (data == NULL) {
		std::cerr << "Decoder Error: insufficient memory\n";
		return -1;
	}
	for (int i=0; i<dataBlocks; i++) {
		memcpy(data+(blockSize*i), blocksArray[i], blockSize);
		//free(blocksArray[i]);
	}
	free(blocksArray);
	return blockSize*dataBlocks - filePad;
}

int Decoder::decodeData(char *&data, char *dataBuf) {
	return decodeData(data, dataBuf, dataBlocks, parityBlocks);
}

bool Decoder::done() {
	return fecSession.IsDecodingComplete((void**)blocksArray);
}
