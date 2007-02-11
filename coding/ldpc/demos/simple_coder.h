/* $Id: simple_coder.h,v 1.1 2006/07/16 06:05:04 alen Exp $ */

/*  LDPC simple FEC encoder sample.
 *  (c) Copyright 2002-2005 INRIA - All rights reserved
 *  Main authors: Christoph Neumann (christoph.neumann@inrialpes.fr)
 *                Vincent Roca      (vincent.roca@inrialpes.fr)
 *		  Julien Laboure   (julien.laboure@inrialpes.fr)
 *
 *  This program is free software; you can redistribute it and/or
 *  modify it under the terms of the GNU General Public License
 *  as published by the Free Software Foundation; either version 2
 *  of the License, or (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
 *  USA.
 */

#ifdef WIN32		/* Windows specific includes */
#include <Winsock2.h>
#include <windows.h>
#else	/* UNIX */	/* Unix specific includes */
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/time.h>	/* for gettimeofday */
#endif	/* OS */

#include "../src/ldpc_fec.h"

/*
 * OS dependant definitions
 */
#ifdef WIN32
#define SLEEP(t)	Sleep(t)
#else
#define SOCKET		int
#define SOCKADDR	sockaddr
#define SOCKADDR_IN	sockaddr_in
#define INVALID_SOCKET	(-1)
#define SOCKET_ERROR	(-1)
#define closesocket	close
#define SLEEP(t)	usleep(t*1000)
#endif	/* OS */


/*
 * Simulation parameters...
 * Change as required
 */
#define PKTSZ	1024		// Packets size, in bytes (multiple of 4).
#define NBDATA	50		// Number of original DATA packets to send.
#define NBFEC	25		// Number of FEC packets to build.
#define NBPKT	(NBDATA+NBFEC)	// Total number of packets to send.
#define LEFT_DEGREE	3	// Left degree of data nodes in the checks graph

/*
 * The Session Type.
 * Can be one of: TypeTRIANGLE, TypeLDGM, TypeSTAIRS, TypeLDPC
 */
//#define SESSION_TYPE	TypeLDPC
//#define SESSION_TYPE	TypeLDGM
//#define SESSION_TYPE	TypeSTAIRS
#define SESSION_TYPE  TypeTRIANGLE

#define SEED		2003	// Seed used to initialize LDPCFecSession

#define VERBOSITY	1	// Define the verbosity level :
				//	0 : no infos
				//	1 : infos
				//	2 : packets dump

#define DEST_IP		"127.0.0.1"	// Destination IP
#define DEST_PORT	10978		// Destination port (UDP)


