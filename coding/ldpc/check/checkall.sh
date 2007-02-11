#!/bin/sh
#
# $Id: checkall.sh,v 1.1 2006/07/16 06:05:02 alen Exp $
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

# top validation script
#
# scans and executes all the elementary test scripts contained in this dir
#

test_sh_list=`ls test_*.sh` 	# sh scripts
test_pl_list=`ls test_*.pl` 	# perl scripts


for t in ${test_sh_list} ${test_pl_list} ; do
	echo ""
	echo ""
	echo "------>   Running test ${t}" 
	./${t}
	val=$?

	if [ ${val} -ne 0 ] ; then
		echo ""
		echo "****** ERROR: Test ${t} failed! Aborting... ******"
		exit
	fi
	echo "<------   Test ${t} passed"
done
echo ""
echo ""
echo "****** All tests succeeded! Validation OK ******"

