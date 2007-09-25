from distutils.core import setup, Extension
import os, sys

class AutoToolsExtension(Extension):
	'''
	provides simple hooks for running ./configure, make, and any pre-configure
	scripts (such as ./bootstrap) necessary to build an Extension package.
	'''
	def __init__(self, name, sources=[], extra_objects=[], include_dirs=[], 
			libraries=[], library_dirs=[], language=[], pre_configure=[],
			run_configure=[], run_make=[]):
		for dir, cmd in pre_configure:
			r = os.system('cd %s; %s' % (dir, cmd))
			if r != 0: sys.exit()
		for dir in run_configure:
			r = os.system('cd %s; ./configure' % dir)
			if r != 0: sys.exit()
		for dir in run_make:
			r = os.system('cd %s; make' % dir)
			if r != 0: sys.exit()
		Extension.__init__(self, name, sources=sources,
				extra_objects=extra_objects, include_dirs=include_dirs,
				libraries=libraries, library_dirs=library_dirs,
				language=language)

setup(name="flud",
		version="0.0.2", 
		description="flud decentralized backup", 
		long_description='a 100% decentralized backup system',
		author="Alen Peacock",
		author_email="apeacock@flud.org",
		url='http://flud.org',
		copyright='(c)2004-2007 Alen Peacock, licensed GPL v3',
		license='GPL v3',
		packages=['flud', 
			'flud.protocol', 
			'flud.bin', 
			'flud.test'],
		package_dir={'flud': 'flud', 
			'flud.protocol': 'flud/protocol',
			'flud.bin': 'flud/bin',
			'flud.test': 'flud/test'},
		package_data={'flud': ['images/*.png']},
		scripts = ['flud/bin/fludnode', 'flud/bin/fludscheduler', 
			'flud/bin/fludclient'],
		ext_modules=[AutoToolsExtension('filecoder',
			pre_configure = [('flud/coding', './bootstrap')],
			run_configure = ['flud/coding'],
			run_make = ['flud/coding/ldpc', 'flud/coding'],
			sources = ['flud/coding/filecodermodule.cpp'],
			extra_objects = ['flud/coding/CodedBlocks.o', 'flud/coding/Coder.o',
				'flud/coding/Decoder.o'],
			include_dirs = ['flud/coding/ldpc/src', 'flud/coding'],
			libraries = ['ldpc', 'stdc++'],
			library_dirs = ['flud/coding/ldpc/bin/linux'],
			language = ['c++'])]
		)


