#ifndef Decoder_CLASS
#define Decoder_CLASS

#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/time.h>
#include <ldpc_fec.h>
#include "CodedBlocks.h"

/**
 * The Decoder object will decode a data stream.
 */
class Decoder {
	private:
		int blockLen, dataBlocks, parityBlocks; 
		int blockSize; // this is the blockLen minus the headerSz
		int leftDegree;
		LDPCFecSession fecSession;
		SessionType sessionType; // could be TypeSTAIRS, TypeLDPC, or TypeTRIANGLE
		int seed;
		char **blocksArray;
		const static int headerSz;

	public:
		/** 
		 * Basic constructor.
		 * @param blockLen the length of a block.
		 * @param dataBlocks number of data blocks (default=40).
		 * @param parityBlocks number of parity blocks (default=20).
		 * @param lefDegree left degree of data nodes in the checks graph 
		 *   (default=3).
		 */
		Decoder(int blockLen, int dataBlocks=40, int parityBlocks=20, 
				int leftDegree=7); 

		/**
		 * Decodes a given stream of data from an array of coded blocks.
		 * @param data data stream is returned by this pointer.  Caller is
		 *   responsible for freeing memory, but not until ::done() returns
		 *   true.
		 * @param databuf the buffer to add to the decode step.  This should be
		 *   blockLen in size.
		 * @param dataBlocks the number of dataBlocks to produce (defaults to
		 *   number set by constructor).
		 * @param parityBlocks the number of parityBlocks to produce (defaults
		 *   to number set by constructor).
		 * @return the length of the decoded data stream, or -1 if decoding was 
		 *   not possible.
		 */
		int decodeData(char *&data, char *databuf, int dataBlocks, 
				int parityBlocks);
		int decodeData(char *&data, char *databuf);

		/**
		 * Returns true if decoding has completed, false otherwise.
		 * @return true if decoding has completed, false otherwise.
		 */
		bool done();
};
#endif
