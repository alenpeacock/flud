from distutils.core import setup, Extension

filecoder = Extension('filecoder',
		sources = ['filecodermodule.cpp'],
		extra_objects = ['CodedBlocks.o', 'Coder.o', 'Decoder.o'],
		include_dirs = ['ldpc/src'],
		libraries = ['ldpc', 'stdc++'],
		library_dirs = ['ldpc/bin/linux'],
		language = ['c++'])

setup (name = 'FileCoding',
		version = '1.0',
		description = 'Module for file coding / decoding',
		ext_modules = [filecoder])
