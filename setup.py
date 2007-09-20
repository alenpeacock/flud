from distutils.core import setup, Extension

setup(name="Flud",
		version="0.0.2", 
		description="Flud Backup", 
		author="Alen Peacock",
		author_email="apeacock@flud.org",
		url='http://flud.org',
		packages=['', 'Protocol'],
		ext_package='filecoder',
		ext_modules=[Extension('filecoder',
			sources = ['coding/filecodermodule.cpp'],
			extra_objects = ['coding/CodedBlocks.o', 'coding/Coder.o', 'coding/Decoder.o'],
			include_dirs = ['coding/ldpc/src'],
			libraries = ['ldpc', 'stdc++'],
			library_dirs = ['coding/ldpc/bin/linux'],
			language = ['c++'])]
		)


