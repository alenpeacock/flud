#!/bin/bash

# builds rpms of all non-mainstream dependencies for flud.
# dependencies are expected to be in directories relative to this script, given
# by the args below. 

# dist, arch and release
dist=fedora
arch=i386
release=8

# directories of dependencies
argparse=argparse-0.8.0
pyutil=pyutil-1.3.6
zfec=zfec-1.2.0-3
flud=../../flud

function dopackage {
	curdir=`pwd`
	dname=$1
	pname=`basename $dname`
	echo "entering $dname"
	pushd $dname
	python setup.py bdist
	python setup.py bdist_rpm
	echo "signing rpms..."
	rpm --resign dist/*.rpm
	rpm -K dist*.rpm
	cp dist/*.$arch.rpm $curdir/yum/$dist/$release/$arch/
	cp dist/*.noarch.rpm $curdir/yum/$dist/$release/$arch/
	cp dist/*.src.rpm $curdir/yum/$dist/
	cp dist/*.tar.gz $curdir/yum/
	echo "installing rpms..."
	if [ -e dist/$pname*.$arch.rpm ]; then
		sudo rpm -Uvh --replacepkgs dist/$pname*.$arch.rpm
	elif [ -e dist/$pname*.noarch.rpm ]; then
		sudo rpm -Uvh --replacepkgs dist/$pname*.noarch.rpm
	else
		# goofy workaround for zfec's conversion of verstring '-' to '_'
		# this just cuts off the last 4 chars of the pname
		sudo rpm -Uvh --replacepkgs dist/${pname:0:${#pname}-4}*.$arch.rpm
	fi
	echo -n "<enter> if okay, <ctrl-c> if not: "
	read
	popd
}

mkdir -p yum/$dist/$release/$arch/

dopackage $argparse
dopackage $pyutil
dopackage $zfec
dopackage $flud

createrepo yum/$dist/$release/$arch
tar cvf yum.$release.$arch.tar yum/
tar rvf yum.$release.$arch.tar *.tar.gz
gzip yum.$release.$arch.tar
