# $Id: Makefile,v 1.1 2006/07/16 06:05:01 alen Exp $
#
# build everything...

# We need the GNU make tool, on some systems it is called
# gmake, on others make is an alias to gmake. Choose one...
#
MAKE = make
#MAKE = gmake


# A phony target is one that is not really the name of a file.
# Using .PHONY prevents problems when a file/dir of the same name
# already exists as is the case here with alc/norm.

.PHONY: all
all: ldpc

# Compile lib with LDPC code
.PHONY: LDPC
LDPC:
	@echo "--------------------"
	@echo "*** LDPC library ***"
	@echo "--------------------"
	cd src; ${MAKE} cleanall; ${MAKE} depend; ${MAKE} LDPC
	@echo "--------------------"
	@echo "*** demos simple_coder/decoder/perf_tool ***"
	@echo "--------------------"
	cd demos; ${MAKE} cleanall; ${MAKE} depend; ${MAKE} LDPC
	@echo "--------------------"
	@echo "*** validation tools ***"
	@echo "--------------------"
	cd check; ${MAKE} cleanall; ${MAKE} depend; ${MAKE} LDPC
	@echo "done"


# Compile lib without LDPC code (default)
.PHONY: ldpc
ldpc:
	@echo "--------------------"
	@echo "*** LDPC library ***"
	@echo "--------------------"
	cd src; ${MAKE} cleanall; ${MAKE} depend; ${MAKE}
	@echo "--------------------"
	@echo "*** demos simple_coder/decoder/perf_tool ***"
	@echo "--------------------"
	cd demos; ${MAKE} cleanall; ${MAKE} depend; ${MAKE}
	@echo "--------------------"
	@echo "*** validation tools ***"
	@echo "--------------------"
	cd check; ${MAKE} cleanall; ${MAKE} depend; ${MAKE}
	@echo "done"


.PHONY: clean
clean:
	@echo "--------------------"
	@echo "*** cleaning LDPC library ***"
	@echo "--------------------"
	cd src; ${MAKE} clean
	@echo "--------------------"
	@echo "*** demos simple_coder/decoder/perf_tool ***"
	@echo "--------------------"
	cd demos; ${MAKE} clean
	@echo "--------------------"
	@echo "*** validation tools ***"
	@echo "--------------------"
	cd check; ${MAKE} clean
	@echo "done"


.PHONY: cleanall
cleanall:
	@echo "--------------------"
	@echo "*** cleaning LDPC library ***"
	@echo "--------------------"
	cd src; ${MAKE} cleanall
	@echo "--------------------"
	@echo "*** demos simple_coder/decoder/perf_tool ***"
	@echo "--------------------"
	cd demos; ${MAKE} cleanall
	@echo "--------------------"
	@echo "*** validation tools ***"
	@echo "--------------------"
	cd check; ${MAKE} cleanall
	@echo "done"

