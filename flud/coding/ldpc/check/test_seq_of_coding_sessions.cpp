/* $Id: test_seq_of_coding_sessions.cpp,v 1.1 2006/07/16 06:05:03 alen Exp $ */

/*  LDPC/LDGM extended performance tool.
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


#define SESSION_NB	500		/* total number of sessions */
#define PKT_SIZE	1024
#define	K		20000		/* number of source packets */
#define N		30000		/* number of source + FEC packets */
#define VERBOSITY	0		/* verbosity level */

/*
 * Various codecs available.
 */
typedef enum {
#ifdef LDPC
	CODEC_LDPC,
#endif	
	CODEC_LDGM,
	CODEC_LDGM_STAIRCASE,
	CODEC_LDGM_TRIANGLE
} codec_t;
#define	CODEC		CODEC_LDGM_STAIRCASE

/* define if supported by LDPC/LDGM lib */
#define LDGM
#define LDGM_STAIRCASE
#define LDGM_TRIANGLE

void init_prg_with_random_seed (int suggested_seed);


int
main (int       argc,
      char      *argv[])
{
	LDPCFecSession	*MyFecSession;
	int		ses;
	int		verbosity = VERBOSITY;
	int		left_degree = 3;
	int		codec = CODEC;
	int		pkt_size = PKT_SIZE;
	int		nbDATA = K;
	int		nbFEC = N-K;
	int		suggested_seed = 0; /* if 0 system chooses random seed*/

	if (pkt_size %4 != 0) {
		EXIT(("ERROR, bad packet size %d, must be multiple of 4\n",
			pkt_size ))
	}
	printf("test_seq_of_coding_sessions: test with %d successive coding sessions...\n", SESSION_NB);
	for (ses = 0; ses < SESSION_NB; ses++) {
		printf(" %d ", ses);
		fflush(NULL);
		MyFecSession = new LDPCFecSession;

		init_prg_with_random_seed(suggested_seed);

		MyFecSession->SetVerbosity(verbosity);
		switch ((int)codec) {
#ifdef LDPC
		case CODEC_LDPC:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size , 
					FLAG_CODER, left_degree, rand(),
					TypeLDPC) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDPC FEC session!\n"))
			}
			break;
#endif
#ifdef LDGM
		case CODEC_LDGM:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size ,
					FLAG_CODER, left_degree, rand(),
					TypeLDGM) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDGM FEC session!\n"))
			}
			break;
#endif
#ifdef LDGM_STAIRCASE
		case CODEC_LDGM_STAIRCASE:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size ,
					FLAG_CODER, left_degree, rand(),
					TypeSTAIRS) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDGM_STAIRCASE FEC session!\n"))
			}
			break;
#endif
#ifdef LDGM_TRIANGLE
		case CODEC_LDGM_TRIANGLE:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size ,
					FLAG_CODER, left_degree, rand(),
					TypeTRIANGLE) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDGM_TRIANGLE FEC session!\n"))
			}
			break;
#endif
		default:
			EXIT(("ERROR: FEC codec %d not supported!\n", codec))
			break;
		}
		/*
		 * close and free everything
		 */
		MyFecSession->EndSession();
		delete MyFecSession;
	}
}


/**
 * Initialize the Pseudo-random number generator with a random seed.
 */
void
init_prg_with_random_seed (int	suggested_seed)
{
	int	seed;	/* random seed for the srand() function */

	if (suggested_seed != 0) {
		seed = suggested_seed;
	} else {
		/* determine our own random seed */
#ifdef WIN32
		seed = timeGetTime();
#else  /* UNIX */
		struct timeval	tv;
		if (gettimeofday(&tv, NULL) < 0) {
			perror("init_prg_with_random_seed: ERROR, gettimeofday() failed:");
			exit(-1);
		}
		seed = (int)tv.tv_usec;
#endif /* OS */
	}
	srand(seed);
	printf("random seed=%d\n", seed);
}


