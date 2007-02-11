#!/bin/sh
#
# $Id: test_several_codecs.sh,v 1.1 2006/07/16 06:05:03 alen Exp $
#
#  Copyright (c) 2002-2005 INRIA - All rights reserved
#  (main author: Vincent Roca - vincent.roca@inrialpes.fr)
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
#  USA.


# test the LDGM codec with an application that opens/closes encoding sessions

host_name=`uname -s`


case ${host_name} in

	Linux)
	bin_path="../bin/linux/eperf_tool"
	;;
	SunOS)
	bin_path="../bin/solaris/eperf_tool"
	;;
	FreeBSD)
	bin_path="../bin/freebsd/eperf_tool"
	;;
	# other OS???? todo
esac

# for debug...
verbosity=''
#verbosity='-v1'
#verbosity='-v2'

echo ""
echo "Running eperf_tool for LDGM"
${bin_path} ${verbosity} -c2 -k20000 -r10000 -l7 -t0
val=$?

echo "returns ${val}"
if [ ${val} -ne 0 ] ; then
	exit 1
fi


echo ""
echo "Running eperf_tool for LDGM Staircase"
${bin_path} ${verbosity} -c2 -k20000 -r10000 -t0
val=$?

echo "returns ${val}"
if [ ${val} -ne 0 ] ; then
	exit 1
fi


echo ""
echo "Running eperf_tool for LDGM Triangle"
${bin_path} ${verbosity} -c3 -k20000 -r10000 -t0
val=$?

echo "returns ${val}"
if [ ${val} -ne 0 ] ; then
	exit 1
fi


echo ""
echo "Running eperf_tool for RSE"
${bin_path} ${verbosity} -c4 -k20000 -r10000 -t0
val=$?

echo "returns ${val}"
if [ ${val} -ne 0 ] ; then
	exit 1
fi


echo ""
echo "Running eperf_tool for LDPC"
${bin_path} ${verbosity} -c0 -k2000 -r1000 -t0
val=$?

echo "returns ${val}"
if [ ${val} -ne 0 ] ; then
	echo ""
	echo "***** WARNING: Please check if library was compiled without LDPC!! *****"
fi

# ok, no problem
exit 0
