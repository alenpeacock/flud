
#ifndef Exception_class
#define Exception_class

#include <string>

/**
 * Generic Exception class. 
 * @author Alen Peacock
 */
class Exception {
	public:
		/**
		 * Default constructor.
		 */
		Exception() : message(""), type("Object") {};
		
		/**
		 * Constructor.
		 * @param s exception message.
		 */
		Exception(std::string s) : message(s), type("Object") {};
		
		/**
		 * Destructor.
		 */
		virtual ~Exception() {};

		/**
		 * Returns the exception's message.
		 * @return the exception's message.
		 */
		virtual std::string getMessage() { return message; }

		/**
		 * Returns a short description of this Exception. 
		 * The result is the concatenation of three strings:
		 *  <ul><li>The name of the actual class of this object
		 *      <li>": " (a colon and a space)
		 *      <li>The result of the getMessage() method for this object </ul>
		 * @return a string representation of this Exception.
		 */
		virtual std::string toString() { return type+": "+message; }

	protected:
		/**
		 * Contains the exception's message.
		 */
		std::string message, type;

		/**
		 * Constructor.
		 * @param type exception type, should always be the class name.
		 * @param s exception message.
		 */
		Exception(std::string type, std::string s) : message(s), type(type) {};
		
};

#endif
