#!/bin/sh
#
# $Id: test_seq_of_coding_sessions.sh,v 1.1 2006/07/16 06:05:03 alen Exp $
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

./test_seq_of_coding_sessions
val=$?

echo "returns ${val}"
if [ ${val} -ne 0 ] ; then
	exit 1
else
	exit 0
fi

