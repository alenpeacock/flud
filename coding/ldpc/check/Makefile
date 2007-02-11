# $Id: Makefile,v 1.3 2006/07/16 06:21:29 alen Exp $
#
# Makefile
#

####### OS Dependant Definitions ######

# they are defined in the following file...
# edit Rules.make as appropriate
include ../Makefile.common


# libraries required
ifeq (${OS},linux)
	# Linux version
	# requires -lpthread
	# add MPATROL support if required
	#
	BINDIR = ../bin/linux
	LIBRARIES = -lc -lm -lpthread
endif

ifeq (${OS},solaris)
	# simple_coder Solaris version:
	# requires -lsocket -lnsl and -L/usr/ucblib -lucb
	#
	BINDIR = ../bin/solaris
	LIBRARIES = -lc -lm -lsocket -lnsl -L/usr/ucblib -lucb -lposix4 -lpthread
endif

ifeq (${OS},freebsd)
	# FreeBSD version
	BINDIR = ../bin/freebsd
	LIBRARIES = -lm -pthread
endif


###### Other variables ######

# Local CFLAGS.

# gcc version
#CFLAGS  = -g -pg -O ${OSFLAGS}
CFLAGS  = -g -O -DDEBUG ${OSFLAGS}
#CFLAGS  = -g -O ${OSFLAGS}

# add purify linker for memory debug (Solaris only).
# Purify 4.0 Solaris 2, Copyright (C) 1992-1996 Pure Software Inc.
#
#CCLINK_PURE = purify $(CC)
CCLINK_PURE = purify  -cache-dir=/tmp $(CC)

# add quantify linker for profiling (Solaris only).
CCLINK_QUANTIFY = /softs/stow/rational/releases/quantify.sol.2002a.06.00/quantify $(CC)

# LDPC library
LDPC_LIBRARY = ${BINDIR}/libldpc.a

# list of source and object files
SRCFILES = test_callbacks_with_perftool.cpp test_seq_of_coding_sessions.cpp test_seq_of_coding_sessions2.cpp
OFILES	 = ${SRCFILES:.cpp=.o}
BINFILES = test_callbacks_with_perftool test_seq_of_coding_sessions test_seq_of_coding_sessions2

###### choose between the LDPC / no-LDPC (default) versions ######

LDPC:	CFLAGS := -DLDPC ${CFLAGS} 

###### Dependancies ######

all: applis

LDPC: applis

# Rule for C++ .cpp extension
.cpp.o:
	$(CC) -c $(CFLAGS) -o $*.o $*.cpp

applis:	${OFILES}
	@echo "** Compiling test_callbacks_with_perftool..."
	${CC} ${CFLAGS} test_callbacks_with_perftool.o ${LIBRARIES} ${LDPC_LIBRARY} -o ./test_callbacks_with_perftool
	@echo "** Compiling test_seq_of_coding_sessions..."
	${CC} ${CFLAGS} test_seq_of_coding_sessions.o ${LIBRARIES} ${LDPC_LIBRARY} -o ./test_seq_of_coding_sessions
	${CC} ${CFLAGS} test_seq_of_coding_sessions2.o ${LIBRARIES} ${LDPC_LIBRARY} -o ./test_seq_of_coding_sessions2
	#${CCLINK_PURE} ${CFLAGS} test_seq_of_coding_sessions.o ${LIBRARIES} ${LDPC_LIBRARY} -o ${BINDIR}/test_seq_of_coding_sessions

clean :
	@for f in core ${OFILES} *_pure* *.pure_* .pur* *purify* ; do \
		if [ -f "$${f}" ] ; then \
			rm "$${f}"; \
		fi \
	done

cleanall : clean
	@for f in ${BINFILES} ; do \
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

test_callbacks_with_perftool.o: test_callbacks_with_perftool.h
test_callbacks_with_perftool.o: ../src/ldpc_fec.h ../src/ldpc_matrix_sparse.h
test_callbacks_with_perftool.o: ../src/tools.h ../src/ldpc_create_pchk.h
test_callbacks_with_perftool.o: ../src/macros.h
test_seq_of_coding_sessions.o: ../src/ldpc_fec.h ../src/ldpc_matrix_sparse.h
test_seq_of_coding_sessions.o: ../src/tools.h ../src/ldpc_create_pchk.h
test_seq_of_coding_sessions.o: ../src/macros.h
test_seq_of_coding_sessions2.o: ../src/ldpc_fec.h ../src/ldpc_matrix_sparse.h
test_seq_of_coding_sessions2.o: ../src/tools.h ../src/ldpc_create_pchk.h
test_seq_of_coding_sessions2.o: ../src/macros.h
