/* $Id: test_seq_of_coding_sessions2.cpp,v 1.1 2006/07/16 06:05:03 alen Exp $ */

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
#define	K		5000		/* number of source packets */
#define N		7500		/* number of source + FEC packets */
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
void	randomize_array (int ** array, int arrayLen);

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
	int		nbPKT = N; /* n parameter */
	int		suggested_seed = 0; /* if 0 system chooses random seed*/

	int		pktseq;		/* data packet sequence number */
	int		fecseq;		/* FEC packet sequence number */
	char		**dataOrig;	/* filled with original data packets AND
					   built FEC packets */
	int		*randOrder;	/* table used by the tx randomization process */

	if (pkt_size %4 != 0) {
		EXIT(("ERROR, bad packet size %d, must be multiple of 4\n",
			pkt_size ))
	}
	printf("test_seq_of_coding_sessions2: test with %d successive coding sessions...\n", SESSION_NB);
		
	MyFecSession = new LDPCFecSession;

	init_prg_with_random_seed(suggested_seed);

	MyFecSession->SetVerbosity(verbosity);

	for (ses = 0; ses < SESSION_NB; ses++) {
		printf(" %d ", ses);
		fflush(NULL);

		switch ((int)codec) {
#ifdef LDPC
		case CODEC_LDPC:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size , 
					FLAG_BOTH, left_degree, rand(),
					TypeLDPC) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDPC FEC session!\n"))
			}
			break;
#endif
#ifdef LDGM
		case CODEC_LDGM:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size ,
					FLAG_BOTH, left_degree, rand(),
					TypeLDGM) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDGM FEC session!\n"))
			}
			break;
#endif
#ifdef LDGM_STAIRCASE
		case CODEC_LDGM_STAIRCASE:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size ,
					FLAG_BOTH, left_degree, rand(),
					TypeSTAIRS) == LDPC_ERROR) {
				EXIT(("ERROR: Unable to initialize LDGM_STAIRCASE FEC session!\n"))
			}
			break;
#endif
#ifdef LDGM_TRIANGLE
		case CODEC_LDGM_TRIANGLE:
			if(MyFecSession->InitSession(nbDATA, nbFEC, pkt_size ,
					FLAG_BOTH, left_degree, rand(),
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
		 * step 2: allocate and generate the original DATA pkts
		 */
		if ((dataOrig = (char**)calloc(nbPKT, sizeof(char*))) == NULL) {
			goto no_mem;
		}
		for (pktseq = 0; pktseq < nbDATA; pktseq++) {
			/*
			 * buffer is 0'ed... Leave it like that, except for the first
			 * four bytes where we copy the pkt seq number.
			 */
			if ((dataOrig[pktseq] = (char*)calloc(pkt_size, 1)) == NULL) {
				goto no_mem;
			}
			*(int *)dataOrig[pktseq] = (int)pktseq;
		}

		/*
		 * step 3: build FEC packets...
		 */
		/* first allocate FEC packet buffers */
		for (fecseq = 0; fecseq < nbFEC; fecseq++) {
			if ((dataOrig[fecseq + nbDATA] = (char*)calloc(pkt_size, 1))
			    == NULL)  {
				goto no_mem;
			}
		}
		
		/* and now do FEC encoding */
		for (fecseq = 0; fecseq < nbFEC; fecseq++) {
			MyFecSession->BuildFecPacket((void**)dataOrig, fecseq,
							dataOrig[fecseq + nbDATA]);
		}

		/*
		 * step 4: randomize pkts order...
		 * this order is used for the "transmissions" of packets
		 */
		if ((randOrder = (int*)calloc(nbPKT, sizeof(int))) == NULL) {
			goto no_mem;
		}
		randomize_array(&randOrder, nbPKT);

		/*
		 * DECODING PART
		 */

		char**	dataDest;
		char*	newPkt;
		int	decodeSteps;	/* decoding step, also index of received pkt */
		int	newPktIdx;

		if ((dataDest = (char**)calloc(nbDATA, sizeof(char*))) == NULL)
		{
			goto no_mem;
		}
		for (decodeSteps = 0; decodeSteps < nbPKT; ) {
			/*
			 * progress in the decoding with the new pkt received,
			 * of index newPktIdx
			 */
			newPktIdx = randOrder[decodeSteps];
			newPkt = dataOrig[newPktIdx];
			ASSERT(newPkt);
			MyFecSession->DecodeFecStep((void**)dataDest, newPkt, newPktIdx, true);
			/* done, incr the step counter now */
			decodeSteps++;
			/* check if completed if we received nbDATA packets or more */
			if (decodeSteps >= nbDATA &&
			   MyFecSession->IsDecodingComplete((void**)dataDest)) {
				/* done! */
				/*
				 * check that data received/recovered is the
				 * same as data sent
				 */
				for (pktseq = 0; pktseq < nbDATA; pktseq++) {
					if (memcmp(dataOrig[pktseq], dataDest[pktseq], pkt_size) != 0 ) {
						EXIT(("ERROR: packet %d received/rebuilt doesn\'t match original\n", pktseq))
					}
				}
			break;
			}
		}
		
		
		/*
		 * close and free everything
		 */
		MyFecSession->EndSession();
		/* free buffer allocated internally for decoded packets */
		for (pktseq = 0; pktseq < nbDATA; pktseq++) {
			if ((dataDest[pktseq] != NULL) &&
			    (dataDest[pktseq] != dataOrig[pktseq])) {
				/* this packet has been decoded by the codec */
				free(dataDest[pktseq]);
			}
		}
		free(dataDest);
		/* free all data and FEC packets created by the source */
		for (pktseq = 0; pktseq < nbPKT; pktseq++) {
			free(dataOrig[pktseq]);
		}
		free(dataOrig);
		free(randOrder);
	}
			
	delete MyFecSession;
	
	return 0;
	
no_mem:
	fprintf(stderr, "ERROR: no memory.\n");
	exit(-1);	
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


/**
 * Randomize an array of integers
 */
void
randomize_array (int	**array,
		 int	arrayLen)
{
	int	backup = 0;
	int	randInd = 0;
	int	i;

	for (i = 0; i < arrayLen; i++ ) {
		(*array)[i] = i;
	}
	for (i = 0; i < arrayLen; i++) {
		backup = (*array)[i];
		randInd = rand() % arrayLen;
		(*array)[i] = (*array)[randInd];
		(*array)[randInd] = backup;
	}
}
