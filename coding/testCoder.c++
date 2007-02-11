#include "Coder.h"
#include "Decoder.h"
#include "CodingException.h"
#include <iostream>

const int dataBlocks = 8;
const int parityBlocks = 16;
const int dataLen = 512;
const int fillInc = 128;

void randomizeArray(int**, int);
void unrandomizeArray(int**, int);

int main(int argc, char* argv[]) {
	char* data = (char*)calloc(dataLen, sizeof(char));

	// fill data with fillInc byte blocks of 0x01.., 0x02.., etc.
	unsigned char fill = 0x01;
	for (unsigned int i=0; i<dataLen; i+=fillInc) {
		memset(data+i, fill, fillInc);
		fill += 0x01;
	}

	std::cout << "original data:\n";
	std::cout << CodedBlocks::toOctets((const unsigned char*)data, dataLen);

	std::cout << "\nNow coding data (n=" << dataBlocks << ", m=" << parityBlocks
		<< ").\n";
	Coder coder(dataBlocks, parityBlocks);
	CodedBlocks coded;
	try {
		coded = coder.codeData(data, dataLen);
	} catch (CodingException& ce) {
		std::cerr << ce.toString() << std::endl;
		return -1;
	}
	free(data);

	std::cout << "coded data contains " << coded.numBlocks << " blocks\n";

	std::cout << "\nNow decoding data:\n";
	char* recoveredData;
	int recDataLen = 0;
	
	int* randOrder = (int*)calloc(dataBlocks+parityBlocks, sizeof(int));
	randomizeArray(&randOrder, dataBlocks+parityBlocks);

	Decoder decoder(coded.blockLen, dataBlocks, parityBlocks);
	int i=0;
	while ((i < dataBlocks+parityBlocks) && (recDataLen <= 0)) {
		//std::cout << "decoding block " << randOrder[i] << ":" << std::endl;
		//std::cout << CodedBlocks::toOctets((const unsigned
		//			char*)coded.blocks[randOrder[i]], coded.blockLen) << std::endl;
		recDataLen = decoder.decodeData(recoveredData, coded.blocks[randOrder[i]]); 
		i++;
	}
	if (recDataLen > 0) {
		std::cout << "finished decoding in " << i << " steps:" << std::endl;
		std::cout << CodedBlocks::toOctets((const unsigned char*)recoveredData, 
				recDataLen);
	} else
		std::cout << "unable to decode after " << i << " steps." << std::endl;
	
	coded.freeBlocks();
	free(recoveredData);
	return 1;
}

/** 
 * Randomize an array of integers
 */
void randomizeArray(int** array, int arrayLen) {
	int backup=0,randInd=0; 
	int seed; /* random seed for the srand() function */
	struct timeval  tv; 
	if (gettimeofday(&tv, NULL) < 0) { 
		perror("randomizeArray: gettimeofday() failed:"); 
		exit(-1); 
	} 
	seed = (int)tv.tv_usec; 
	srand(seed); 
	for( int i=0; i<arrayLen; i++ ) 
		(*array)[i]=i;
									                                                                                
	for( int i=0; i<arrayLen; i++ ) { 
		backup = (*array)[i];
		randInd = rand()%arrayLen; 
		(*array)[i] = (*array)[randInd]; (*array)[randInd] = backup; 
	}
}

void unrandomizeArray(int** array, int arrayLen) {
	for( int i=0; i<arrayLen; i++ ) 
		(*array)[i]=i;
}
