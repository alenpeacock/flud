#include "CodedBlocks.h"
#include <iostream>

const int CodedBlocks::headerSz = 8;

CodedBlocks::CodedBlocks() {
	blocks = NULL;
	numBlocks = 0;
	blockLen = 0;
}

CodedBlocks::CodedBlocks(char* block, int len, int totalBlocks) {
	this->blocks = (char**)calloc(totalBlocks, sizeof(char*));
	this->blocks[0] = block;
	numBlocks = totalBlocks;
	blockLen = len;
}

CodedBlocks::CodedBlocks(char** blocks, int blockLen, int numBlocks) {
	this->blocks = blocks;
	this->blockLen = blockLen;
	this->numBlocks = numBlocks;
}

CodedBlocks::CodedBlocks(const CodedBlocks& c) {
	blocks = c.blocks;
	blockLen = c.blockLen;
	numBlocks = c.numBlocks;
}

CodedBlocks::~CodedBlocks() {
}

void CodedBlocks::addBlock(char* block, int blockLen) {
	if (blocks == NULL)
		this->blocks = (char**)calloc(numBlocks, sizeof(char*));
	if (this->blockLen != 0 && this->blockLen != blockLen) {
		std::cerr << "warning, illegal blockLen!" << std::endl;
	}
	this->blocks[numBlocks++] = block;
	this->blockLen = blockLen;
	//printOctets((const unsigned char*)this->blocks[numBlocks-1], blockLen);
}

void CodedBlocks::freeBlocks() {
	if (blocks != NULL) {
		for (int i=0; i<numBlocks; i++) {
			free(blocks[i]);
		}
		free(blocks);
	}
};

const CodedBlocks& CodedBlocks::operator=(const CodedBlocks &c) {
	if (&c != this) {
		blocks = c.blocks;
		blockLen = c.blockLen;
		numBlocks = c.numBlocks;
	}
	return *this;
}

void CodedBlocks::printOctets(const unsigned char *buf, int length) {
	int i;
  int line_count=0, col_count=0;
	for (i=0; i<length; i++) {
		if (col_count % 16 == 0) {
			// beginning of line index
			printf("%04hx ",i);
		}
		if (col_count % 8 == 0) {
			// extra convenience spacing
			printf(" ");
		}
		// show the byte
		printf("%02hx ",buf[i]);
		col_count++;
		if ((col_count) % 16 == 0 || i+1 >= length) {
			// end of line
			printf("\n");
			line_count++;
		}
	}
}
	
std::string CodedBlocks::toOctets(const unsigned char *buf, int length) {
	char result[(length/16+1)*80];
	char *result_p = result;
	char asciiline[20];
	char *asciiline_p = asciiline;
	int i;
  int line_count=0, col_count=0;
	for (i=0; i<length; i++) {
		if (col_count % 16 == 0) {
			// beginning of line index
			sprintf(result_p, "%04hx ",i);
			result_p += 5;
		}
		if (col_count % 8 == 0) {
			// extra convenience spacing
			sprintf(result_p, " ");
			result_p += 1;
			sprintf(asciiline_p, " ");
			asciiline_p += 1;
		}
		// show the byte
		sprintf(result_p, "%02hx ",buf[i]);
		result_p += 3;
		col_count++;
		if (buf[i] >= (unsigned char)' ' && buf[i] <= (unsigned char)'~') {
			sprintf(asciiline_p, "%c",buf[i]);  // add to ascii text if viewable...
		} else {
			sprintf(asciiline_p, ".");  // ...otherwise '.'
		}
		asciiline_p++;
		if (i+1 >= length) {
			// end of data
			int pad = 16 - (col_count - (16 * line_count));
			if (pad >= 8) { // convenience spacing pad
				sprintf(result_p," ");
				result_p++;
			}
			for (int j=0; j<pad; j++) { // missing columns pad
				sprintf(result_p,"   ");
				result_p += 3;
			}
		}
		if ((col_count) % 16 == 0 || i+1 >= length) {
			// end of line
			sprintf(result_p," %s",asciiline); // add ascii text
			result_p += col_count - (16 * line_count) + 3;
			if (col_count <= 8) result_p--;
			asciiline_p = asciiline; // reset ascii text
			sprintf(result_p,"\n");
			result_p += 1;
			line_count++;
		}
	}
	sprintf(result_p,"\0");
	return std::string(result);

}
