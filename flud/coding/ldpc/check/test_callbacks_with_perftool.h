
/*  LDPC performance tool with callbacks.
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
#include <ctype.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/time.h>	/* for gettimeofday */
#endif	/* OS */
#include <stdlib.h>

#include "../src/ldpc_fec.h"
#include "../src/macros.h"

#ifdef WIN32
#include "../src/getopt.h"
#endif

/*
 * OS dependant definitions
 */
#if defined(LINUX) || defined(SOLARIS)
#define SOCKET		int
#define SOCKADDR	sockaddr
#define	SOCKADDR_IN	sockaddr_in
#define INVALID_SOCKET	(-1)
#define SOCKET_ERROR	(-1)
#endif	/* OS */


/*
 * Default simulation parameters
 */
#define PKTSZ	1024	// Packets size, in bytes (multiple of 4).
#define NBDATA	2000	// Number of original DATA packets to send.
#define NBFEC	1000		// Number of FEC packets to build.
#define NBPKT	(NBDATA+NBFEC)	// Total number of packets to send.
#define LEFT_DEGREE	3	// Left degree of data nodes in the bipartite
						// graph
#define VERBOSITY	0	// Define the verbosity level

// If defined, then check if rebuilt packets match original ones
#define CHECK_INTEGRITY


/**
 * Dummy structure used to store all packets.
 * This is the structure pointed to by the various LDPCFecSession tables!
 */
typedef struct {
	int	unused;		// needed to check that struct and buf
				// are not aligned
	char	*buf;		// pointer to buffer containing the packet
} pkt_t;

