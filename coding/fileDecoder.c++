/**
 * Decodes a given file.  Takes as argument a stem filename, and creates 
 * a decoded file stem.decoded as a result.
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
	if (argc != 4) {
		std::cerr << "takes as argument a stem filename and produces a"
			<< " decoded file \"stem.coded\"\n";
		std::cerr << "usage: " << argv[0] << " n m stem\n";
		std::cerr << "       where n = data chunks, m = coding (parity) chunks.\n";
		exit(-1);
	}
	int dataBlocks = atoi(argv[1]);
	int parityBlocks = atoi(argv[2]);
	std::string stem = argv[3];
	
	Decoder *decoder = NULL;

	char* recoveredData = NULL;
	int recDataLen = 0;
	char filename[256];
	int numBlocksRead = 0;
	for (int i=0; i<dataBlocks+parityBlocks; i++) {
		sprintf(filename,"%s-%04d",stem.c_str(),i);
		std::cout << "trying to open " << filename << std::endl;
		int fd;
		if ((fd = open(filename, O_RDONLY, 0)) == -1) {
			std::cerr << "unable to open " << filename << std::endl;
		} else {
			std::cout << "successfully opened " << filename << std::endl;
			struct stat statbuf;
			if (fstat(fd, &statbuf) != 0) {
				std::cerr << "unable to stat " << filename << std::endl;
				exit(-1);
			}
			int dataLen = statbuf.st_size;
			if (decoder == NULL) {
				decoder = new Decoder(dataLen, dataBlocks, parityBlocks);
			}
			char *databuf = new char[dataLen];
			int res = 0;
			do {
				res += read(fd, databuf, dataLen);
			} while (res < dataLen);
			numBlocksRead++;
			//std::cout << "data: ";  
			//for (int i=0; i<res; i++) {
			//	std::cout << databuf[i];
			//}
			//std::cout << std::endl;
			std::cout << "read " << res << " bytes of data, attempting decode " 
				<< std::endl;
			recDataLen = decoder->decodeData(recoveredData, databuf);
			if (recDataLen > 0) {
				std::cout << "recovered all " << recDataLen << " bytes of file after " 
					<< "reading " << numBlocksRead << " blocks." << std::endl;
				break;
			}
			//delete [] databuf;
			if (decoder->done()) {
				break;
			}
		}
	}
	if (recDataLen > 0) {
		int fd2;
		char filename[256];
		sprintf(filename,"%s.recovered",stem.c_str());
		if ((fd2 = creat(filename, 0644)) == -1) {
			std::cerr << "unable to open '" << filename << "' for writing" 
				<< std::endl;
		} else {
			int res = write(fd2, recoveredData, recDataLen);
		}
	} else {
		std::cout << "unable to recover file after " << numBlocksRead << " blocks." 
			<< std::endl;
	}
	free(recoveredData);
	delete decoder;

}
