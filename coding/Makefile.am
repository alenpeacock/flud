AUTOMAKE_OPTIONS = foreign

CLEANFILES	= *~

SUBDIRS		= . 
EXTRA_DIST	= configure

LDFLAGS =
LIBS = -Lldpc/bin/linux -lldpc
INCLUDES = -Ildpc/src

# since config/ is used for many internal files, we need to copy them for dist

AUX_DIST = 	$(ac_aux_dir)/config.guess \
		$(ac_aux_dir)/config.sub \
		$(ac_aux_dir)/install-sh \
		$(ac_aux_dir)/missing \
		$(ac_aux_dir)/mkinstalldirs
AUX_DIST_EXTRA =

SRCS = \
	CodedBlocks.c++ CodedBlocks.h \
	Coder.c++ Coder.h \
	Decoder.c++ Decoder.h \
	Exception.h CodingException.h

lib_LIBRARIES = libCode.a
libCode_a_SOURCES = $(SRCS)

bin_PROGRAMS = testCoder fileDecoder fileCoder 

testCoder_SOURCES = testCoder.c++ $(SRCS)
testCoder_LDADD = $(LOCAL_LIBS)
testCoder_DEPENDENCIES = $(LOCAL_LIBS)

fileCoder_SOURCES = fileCoder.c++ $(SRCS)
fileCoder_LDADD = $(LOCAL_LIBS)
fileCoder_DEPENDENCIES = $(LOCAL_LIBS)

fileDecoder_SOURCES = fileDecoder.c++ $(SRCS)
fileDecoder_LDADD = $(LOCAL_LIBS)
fileDecoder_DEPENDENCIES = $(LOCAL_LIBS)

depend:	depend-recursive
	touch make.depend
	makedepend -f make.depend 2> /dev/null -- $(CXXCOMPILE) $(COMPILE) -- $(SOURCES) 

-include make.depend


