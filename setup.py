from setuptools import setup, Extension
import os, sys

setup(name="flud",
		version="0.2.1", 
		description="flud decentralized backup", 
		long_description='a 100% decentralized backup system',
		author="Alen Peacock",
		author_email="apeacock@flud.org",
		url='http://flud.org',
		license='GPLv3 (c)2004-2007 Alen Peacock',
		packages=['flud', 
			'flud.protocol', 
			'flud.bin', 
			'flud.test'],
		package_dir={'flud': 'flud', 
			'flud.protocol': 'flud/protocol',
			'flud.bin': 'flud/bin',
			'flud.test': 'flud/test'},
		package_data={'flud': 
				['images/*.png', 'fludrules.init']},
		scripts = ['flud/bin/fludnode',
			'flud/bin/fludscheduler', 
			'flud/bin/fludlocalclient',
			'flud/bin/flud-manifestViewer',
			'flud/bin/flud-metadataViewer',
			'flud/bin/start-fludnodes', 
			'flud/bin/stop-fludnodes',
			'flud/bin/clean-fludnodes']
)
