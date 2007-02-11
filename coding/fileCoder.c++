/**
 * Codes a given file.  Takes as argument a filename, and writes
 * filename.coded/block#### as a result.
 */
 
#include "Coder.h"
#include "Decoder.h"
#include "CodingException.h"
#include <iostream>
#include <sstream>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

int main(int argc, char* argv[]) {
	if (argc != 5) {
		std::cerr << "takes a file and produces a coded version as "
			<< "a series of files named stem-####\n";
		std::cerr << "usage: " << argv[0] << " filename n m stem\n";
		std::cerr << "       where n = data chunks, m = coding (parity) chunks.\n";
		exit(-1);
	}
	int dataBlocks = atoi(argv[2]);
	int parityBlocks = atoi(argv[3]);
	std::string stem = argv[4];
	
	Coder coder(dataBlocks,parityBlocks);

	int fd;
	if ((fd = open(argv[1], O_RDONLY, 0)) == -1) {
		std::cerr << "unable to open " << argv[1] << std::endl;
		exit(-1);
	}
	struct stat statbuf;
	if (fstat(fd, &statbuf) != 0) {
		std::cerr << "unable to stat " << argv[1] << std::endl;
		exit(-1);
	}
	int dataLen = statbuf.st_size;
	//char data[dataLen];
	char *data = (char*)malloc(dataLen);
	if (data == NULL) {
		printf("couldn't allocate memory for file read\n");
		exit(-1);
	}

	int i=0;
	int bytesread=0;
	while ((i = read(fd, data, dataLen)) > 0) {
		bytesread += i;
	}
	if (i < 0) {
		printf("error reading file.  Can't continue.\n");
		exit(-1);
	}
	close(fd);

	// code the data
	CodedBlocks coded;
	try {
		coded = coder.codeData(data, dataLen);
	} catch (CodingException& ce) {
		std::cerr << ce.toString() << std::endl;
		return -1;
	}

	// write the coded data to files
	for (int i=0; i<coded.numBlocks; i++) {
		char newfile[255];
		sprintf(newfile,"%s-%04d",stem.c_str(),i);
		if ((fd = creat(newfile, 0666)) < 0) {
			std::cerr << "unable to open " << newfile << std::endl;
			exit(-1);
		}
		int byteswritten = 0;
		while (byteswritten < coded.blockLen) {
			int ret = write(fd, coded.blocks[i]+byteswritten, 
					coded.blockLen-byteswritten);
			byteswritten += ret;
			if (ret < 0) {
				std::cerr << "unable to write to " << newfile << std::endl;
				exit(-1);
			}
		}
	}
	close(fd);

	coded.freeBlocks();
	return 1;
}
