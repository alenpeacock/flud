#ifndef CodedBlocks_CLASS
#define CodedBlocks_CLASS

#include <iostream>

/**
 * Helper class for Coder/Decoder classes.  Represents coded blocks of data.
 */
class CodedBlocks {
	public:
		char** blocks;
		int blockLen;
		int numBlocks;
		static const int headerSz;

		/** Simple constructor.
		 */
		CodedBlocks();

		/** Constructor with single block param.  Useful to initialize a new
		 * CodedBlock where you only have the first block (others coming in as
		 * a stream, added with ::addBlock()).
		 * @param block the block to add.  This memory must not be released by the
		 * caller, i.e., CodedBlocks owns it.
		 * @param len the length of this block.
		 * @param numBlocks the number of blocks total.
		 */
		CodedBlocks(char* block, int len, int numBlocks);

		/**
		 * Constructor uses the data pointed to by blocks, and the description
		 * of the size of that data by blockLen and numBlocks.
		 */
		CodedBlocks(char** blocks, int blockLen, int numBlocks);

		/**
		 * Copy constructor.  Does not copy memory in blocks, but maintains another
		 * pointer to it.
		 */
		CodedBlocks(const CodedBlocks& c);
		
		/**
		 * Simple destructor.  DOES NOT free memory pointed to by blocks.
		 */
		~CodedBlocks(); 

		/**
		 * Adds a block to the CodedBlock.
		 * @param block the block to add.  The block must be of the correct
		 * length, and must not be freed by the caller, i.e., CodedBlocks owns it.
		 */
		void addBlock(char* block, int dataLen);

		/**
		 * Will free the memory pointed to by blocks.
		 */
		void freeBlocks();

		/**
		 * Assignment operator.  Does not copy memory.
		 */
		const CodedBlocks& operator=(const CodedBlocks &c);

		static std::string toOctets(const unsigned char* buf, int length);
		
		/**
		 * Convenience method.  Prints the contents of buf in hexadecimal, 
		 * nicely formatted.
		 */
		static void printOctets(const unsigned char* buf, int length);
};

#endif
