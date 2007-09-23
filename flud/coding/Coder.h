#ifndef Coder_CLASS
#define Coder_CLASS

#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/time.h>
#include <ldpc_fec.h>
#include "CodedBlocks.h"

/**
 * The Coder object will code a data stream.
 */
class Coder {
	private:
		int dataBlocks, parityBlocks, blockSize;
		int leftDegree;
		SessionType sessionType; // could be TypeSTAIRS, TypeLDPC, or TypeTRIANGLE
		int seed;
		LDPCFecSession fecSession;
		const static int headerSz;

	public:
		/** 
		 * Basic constructor.
		 * @param dataBlocks number of data blocks (default=40).
		 * @param parityBlocks number of parity blocks (default=20).
		 * @param lefDegree left degree of data nodes in the checks graph 
		 *   (default=7).
		 */
		Coder(int dataBlocks=40, int parityBlocks=20, int leftDegree=7); 

		/**
		 * Codes a given stream of data, returning a CodedBlocks object containg
		 * an array of coded blocks.
		 * @param data the stream of data to code.  This data should be freed
		 *   by the caller when no longer needed, but no sooner than after this
		 *   method returns.
		 * @param length the length of the data stream.
		 * @param dataBlocks the number of dataBlocks to produce (defaults to
		 *   number set by constructor).
		 * @param parityBlocks the number of parityBlocks to produce (defaults
		 *   to number set by constructor).
		 * @return a CodedBlocks object containing the coded data sub-blocks 
		 *   (data+parity), and which should be freed by the caller when no
		 *   longer needed.
		 * @throws CodingException if cannot perform coding operation.
		 */
		CodedBlocks codeData(char* data, int length,
				int dataBlocks, int parityBlocks);

		CodedBlocks codeData(char* data, int length);
		
		int getBlockSize();
};
#endif
