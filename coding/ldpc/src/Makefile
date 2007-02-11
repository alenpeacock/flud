# $Id: Makefile,v 1.3 2006/07/16 06:21:29 alen Exp $
#
# Makefile
#

###### OS Dependant Definitions ######

# they are defined in the following file...
# edit Makefile.common as appropriate
include ../Makefile.common


ifeq (${OS},linux)
	# Linux version
	# A few libs for memory debug:
	# -lefence	for memory debug on Linux (and other plateforms)
	#		Requires: export EF_PROTECT_FREE=1
	#			  export EF_PROTECT_BELOW=1
	#
	#LIBRARIES = -Wl,-Bstatic -lefence -Wl,-Bdynamic -lc -lm -lpthread
	LIBRARIES = -lc -lm -lpthread 
	BINDIR = ../bin/linux
endif

ifeq (${OS},solaris)
	# Solaris version: requires -lsocket -lnsl and -L/usr/ucblib -lucb
	#
	LIBRARIES = -lc -lm -lsocket -lnsl -L/usr/ucblib -lucb -lpthread
	BINDIR = ../bin/solaris
endif

ifeq (${OS},freebsd)
	# FreeBSD version
	BINDIR = ../bin/freebsd
	LIBRARIES = -lm -pthread
endif


###### Other Variables ######

# List of source, object and include files
#
SRCFILES  = ldpc_create_pchk.cpp ldpc_fec.cpp tools.cpp ldpc_matrix_sparse.cpp ldpc_rand.cpp
OFILES = ${SRCFILES:.cpp=.o}
SRCFILES_LDPC  = ldpc_matrix_dense.cpp ldpc_matrix_convert.cpp ldpc_create_gen.cpp
OFILES_LDPC = ${SRCFILES_LDPC:.cpp=.o}
#ldpc_INC_FILES = 


# General purpose local FLAGS.
# WARNING: with gcc/g++, never use -O3 optimisation (compiler bugs)
#
#CFLAGS	= ${OSFLAGS} -DDEBUG -g		# for debug version
#CFLAGS	= ${OSFLAGS} -O 		# for optimized version
CFLAGS	= ${OSFLAGS} -O -g 		# for optimized version
#CFLAGS	= ${OSFLAGS} -O -g -pg 		# optimized with profiling

LDFLAGS  =


###### choose between the LDPC / no-LDPC (default) versions ######

LDPC:	CFLAGS := -DLDPC ${CFLAGS} 

###### Dependancies ######
# by default, create the MCL lib
all: lib

# Rule for C++ .cpp extension
.cpp.o:
	$(CC) -c $(CFLAGS) -o $*.o $*.cpp

# Compile lib with LDPC code
LDPC: ${OFILES} ${OFILES_LDPC}
	@echo "** Create the LDPC library..."
	${AR} -rcsv ${BINDIR}/libldpc.a ${OFILES} ${OFILES_LDPC}
	@echo "done"

# Compile lib without LDPC code (default)
lib : ${OFILES}
	@echo "** Create the LDPC library..."
	${AR} -rcsv ${BINDIR}/libldpc.a ${OFILES}
	@echo "done"

tags:
	etags $(SRCS)

clean :
	@for f in core ${OFILES} ${OFILES_LDPC}; do \
		if [ -f "$${f}" ] ; then \
			rm "$${f}"; \
		fi \
	done

cleanall : clean
	@for f in ${BINDIR}/libldpc.a ${BINDIR}/*.pchk ; do \
		if [ -f "$${f}" ] ; then \
			rm $${f} ; \
		fi \
	done

depend :
	# Use -Y to prevent including the system header files that won't
	# change. Send all error messages to /dev/null
	${DEPEND} -- ${CFLAGS} -Y -- ${SRCFILES} 2>/dev/null


# Dependencies automatically created by makedepend (see depend target above).
#
# DO NOT DELETE THIS LINE -- make depend depends on it.

ldpc_create_pchk.o: ldpc_create_pchk.h ldpc_matrix_sparse.h tools.h
ldpc_create_pchk.o: ldpc_rand.h
ldpc_fec.o: ldpc_fec.h ldpc_matrix_sparse.h tools.h ldpc_create_pchk.h
ldpc_fec.o: macros.h
tools.o: tools.h
ldpc_matrix_sparse.o: ldpc_matrix_sparse.h tools.h
ldpc_rand.o: ldpc_rand.h
