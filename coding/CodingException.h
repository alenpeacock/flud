// CodingException class

#ifndef CodingException_class
#define CodingException_class

#include <string>
#include "Exception.h"


/**
 * Thrown when a coding encounters an error condition. 
 * @author Alen Peacock
 */
class CodingException : public Exception {
	public:
		/**
		 * Default constructor.
		 */
		CodingException() : Exception("CodingException","") {};
		/**
		 * Constructor.
		 * @param s exception message.
		 */
		CodingException(std::string s) : Exception("CodingException",s) 
			{};
		/**
		 * Destructor.
		 */
		virtual ~CodingException() {};

};

#endif
