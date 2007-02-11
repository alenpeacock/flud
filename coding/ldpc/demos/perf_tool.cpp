/* $Id: perf_tool.cpp,v 1.1 2006/07/16 06:05:04 alen Exp $ */

/*  LDPC performance tool.
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

#include "perf_tool.h"


/*
 * Global variables.
 */
int	nbDATA		= NBDATA;	  /* k parameter */
int	nbFEC		= NBFEC;	  /* n - k parameter */
int	nbPKT		= NBDATA + NBFEC; /* n parameter */
int	pktSize		= PKTSZ;	  /* packet size */
int	left_degree	= LEFT_DEGREE;	  /* left degree in bipartite graph */
int	verbosity	= VERBOSITY;	  /* verbosity 0: nothing, 1: all */


/* Functions prototypes */
void	init_prg_with_random_seed ();
void 	ParseCommandLine (int argc, char *argv[]);
void	printUsage (char *cmdName);
void	randomize_array (int ** array, int arrayLen);



/**
 * Entry point for this application.
 */
int
main   (int	argc,
	char	**argv )
{
	LDPCFecSession	MyFecSession;
	int	pktseq;		/* data packet sequence number */
	int	fecseq;		/* FEC packet sequence number */
	char	**dataOrig;	/* filled with original data packets AND
				   built FEC packets */
	int	*randOrder;	/* table used by the tx randomization process */

#ifdef WIN32
	LARGE_INTEGER tv0;	/* start */
	LARGE_INTEGER tv1;	/* end */
	LARGE_INTEGER freq;
	QueryPerformanceFrequency(&freq);
#else
	struct timeval	tv0;	/* start */
	struct timeval	tv1;	/* end */
	struct timeval	tv_delta;/* difference tv1 - tv0 */
#endif	// OS_DEP

	ParseCommandLine(argc, argv);

	if (pktSize%4 != 0) {
		EXIT(("ERROR, bad packet size %d, must be multiple of 4\n",
			pktSize))
	}
	init_prg_with_random_seed();

	/*
	 * CODING PART
	 */

	/*
	 * step 1: initialize the LDPC FEC session
	 */
#ifdef WIN32
	QueryPerformanceCounter(&tv0);
	printf("init_start=%lI64f\n", (double)tv0.QuadPart/(double)freq.QuadPart);
#else
	gettimeofday(&tv0, NULL);
	printf("init_start=%ld.%ld\n", tv0.tv_sec, tv0.tv_usec);
#endif
	MyFecSession.SetVerbosity(verbosity);

//#define LDGM_TRIANGLE
#define LDGM_STAIRS
//#define LDGM
//#define LDPC
#ifdef LDGM_STAIRS
	if(MyFecSession.InitSession(nbDATA, nbFEC, pktSize, FLAG_BOTH, left_degree, rand(), TypeSTAIRS) == LDPC_ERROR)
#elif defined (LDGM_TRIANGLE)
	if(MyFecSession.InitSession(nbDATA, nbFEC, pktSize, FLAG_BOTH, left_degree, rand(), TypeTRIANGLE) == LDPC_ERROR)
#elif defined (LDGM)
	if(MyFecSession.InitSession(nbDATA, nbFEC, pktSize, FLAG_BOTH, left_degree, rand(), TypeLDGM) == LDPC_ERROR)
#elif defined (LDPC)
	if(MyFecSession.InitSession(nbDATA, nbFEC, pktSize, FLAG_BOTH, left_degree, rand(), TypeLDPC) == LDPC_ERROR)
#endif // codec
	{
		EXIT(("ERROR: Unable to initialize FEC session!\n"))
	}

#ifdef WIN32
	QueryPerformanceCounter(&tv1);
	printf("init_end=%I64f  init_time=%I64f\n",
		(double)tv1.QuadPart/(double)freq.QuadPart,
		(double)(tv1.QuadPart-tv0.QuadPart)/(double)freq.QuadPart );

#else
	gettimeofday(&tv1, NULL);
	timersub(tv1, tv0, tv_delta);
	printf("init_end=%ld.%ld  init_time=%ld.%06ld\n",
		tv1.tv_sec, tv1.tv_usec, tv_delta.tv_sec, tv_delta.tv_usec);
#endif
	MyFecSession.MoreAbout(stdout);
	printf("\nLDPC/LDGM performance tool\ndata_pkts=%d  fec_pkts=%d  pkt_size=%d  left_degree=%d\n\n",
		nbDATA, nbFEC, pktSize, left_degree);

	/*
	 * step 2: allocate and generate the original DATA pkts
	 */
	PRINT_LVL(1, ("\nAllocating and generating random DATA packets...\n"))
	if ((dataOrig = (char**)calloc(nbPKT, sizeof(char*))) == NULL) {
		goto no_mem;
	}
	for (pktseq = 0; pktseq < nbDATA; pktseq++) {
		/*
		 * buffer is 0'ed... Leave it like that, except for the first
		 * four bytes where we copy the pkt seq number.
		 */
		if ((dataOrig[pktseq] = (char*)calloc(pktSize, 1)) == NULL) {
			goto no_mem;
		}
		*(int *)dataOrig[pktseq] = (int)pktseq;
	}

	/*
	 * step 3: build FEC packets...
	 */
	/* first allocate FEC packet buffers */
	for (fecseq = 0; fecseq < nbFEC; fecseq++) {
		if ((dataOrig[fecseq + nbDATA] = (char*)calloc(pktSize, 1))
		    == NULL)  {
			goto no_mem;
		}
	}
	PRINT_LVL(1, ("Building FEC packets...\n"))
#ifdef WIN32
	QueryPerformanceCounter(&tv0);
	printf("build_fec_start=%lI64f\n", (double)tv0.QuadPart/(double)freq.QuadPart);
#else
	gettimeofday(&tv0, NULL);
	printf("build_fec_start=%ld.%ld\n", tv0.tv_sec, tv0.tv_usec);
#endif
	/* and now do FEC encoding */
	for (fecseq = 0; fecseq < nbFEC; fecseq++) {
		MyFecSession.BuildFecPacket((void**)dataOrig, fecseq,
						dataOrig[fecseq + nbDATA]);
	}
#ifdef WIN32
	QueryPerformanceCounter(&tv1);
	printf("build_fec_end=%I64f  build_fec_time=%I64f\n",
		(double)tv1.QuadPart/(double)freq.QuadPart,
		(double)(tv1.QuadPart-tv0.QuadPart)/(double)freq.QuadPart );

#else
	gettimeofday(&tv1, NULL);
	timersub(tv1, tv0, tv_delta);
	printf("build_fec_end=%ld.%ld  build_fec_time=%ld.%06ld\n",
		tv1.tv_sec, tv1.tv_usec, tv_delta.tv_sec, tv_delta.tv_usec);
#endif

	/*
	 * step 4: randomize pkts order...
	 * this order is used for the "transmissions" of packets
	 */
	PRINT_LVL(1, ("Randomizing packets...\n"))
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

	PRINT_LVL(1, ("Decoding in progress...\n"))
#ifdef WIN32
	QueryPerformanceCounter(&tv0);
	printf("decoding_start=%lI64f\n", (double)tv0.QuadPart/(double)freq.QuadPart);
#else
	gettimeofday(&tv0, NULL);
	printf("decoding_start=%ld.%ld\n", tv0.tv_sec, tv0.tv_usec);
#endif
	if ((dataDest = (char**)calloc(nbDATA, sizeof(char*))) == NULL)
//	    || (newPkt = (char*)calloc(pktSize, 1)) == NULL)
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
		PRINT_LVL(1, ("------ step %d, recv pkt %d ------\n",
			decodeSteps, newPktIdx))
		MyFecSession.DecodeFecStep((void**)dataDest, newPkt, newPktIdx, true);
		/* done, incr the step counter now */
		decodeSteps++;
		/* check if completed if we received nbDATA packets or more */
		if (decodeSteps >= nbDATA &&
		    MyFecSession.IsDecodingComplete((void**)dataDest)) {
			/* done! */
#ifdef WIN32
			QueryPerformanceCounter(&tv1);
			printf("decoding_end=%I64f  decoding_time=%I64f  decoding_steps=%d  inefficiency_ratio=%.3f\n",
				(double)tv1.QuadPart/(double)freq.QuadPart,
				(double)(tv1.QuadPart-tv0.QuadPart)/(double)freq.QuadPart,
				decodeSteps, (float)decodeSteps/(float)nbDATA);
#else
			gettimeofday(&tv1, NULL);
			timersub(tv1, tv0, tv_delta);
			printf("decoding_end=%ld.%ld  decoding_time=%ld.%06ld  decoding_steps=%d  inefficiency_ratio=%.3f\n",
				tv1.tv_sec, tv1.tv_usec,
				tv_delta.tv_sec, tv_delta.tv_usec,
				decodeSteps, (float)decodeSteps/(float)nbDATA);
#endif

			PRINT_LVL(1, ("Done! All DATA packets rebuilt in %d steps\n",
				decodeSteps))
#ifdef CHECK_INTEGRITY
			/*
			 * check that data received/recovered is the
			 * same as data sent
			 */
			PRINT_LVL(1, ("Now checking DATA integrity...\n"))
			for (pktseq = 0; pktseq < nbDATA; pktseq++) {
				if (memcmp(dataOrig[pktseq], dataDest[pktseq], pktSize) != 0 ) {
					EXIT(("ERROR: packet %d received/rebuilt doesn\'t match original\n", pktseq))
				}
			}
			PRINT_LVL(1, ( "Mission accomplished, all data packets OK!\nLeaving...\n" ))
#endif // CHECK_INTEGRITY
			break;
		}
	}
	if (decodeSteps >= nbPKT) {
#ifdef WIN32
		QueryPerformanceCounter(&tv1);
		printf("decoding_end=%I64f  decoding_time=%I64f  decoding_steps=-1, decoding_failed\n",
			(double)tv1.QuadPart/(double)freq.QuadPart,
			(double)(tv1.QuadPart-tv0.QuadPart)/(double)freq.QuadPart);
#else
		gettimeofday(&tv1, NULL);
		timersub(tv1, tv0, tv_delta);
		printf("decoding_end=%ld.%ld  decoding_time=%ld.%06ld  decoding_steps=-1, decoding_failed\n",
			tv1.tv_sec, tv1.tv_usec,
			tv_delta.tv_sec, tv_delta.tv_usec);
#endif
		printf("ERROR: all packets received but decoding failed!\n");
	}
	/*
	 * close and free everything
	 */
	MyFecSession.EndSession();
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
	return 0;

no_mem:
	fprintf(stderr, "ERROR: no memory.\n");
	exit(-1);
}


/**
 * Initialize the Pseudo-random number generator with a random seed.
 */
void
init_prg_with_random_seed ()
{
	int	seed;	/* random seed for the srand() function */

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
	srand(seed);

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

	init_prg_with_random_seed();
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


/**
 * Print "usage" message to user
 */
void
printUsage (char *cmdName)
{
	printf("LDPC performance evaluator\n");
	printf("(c) Copyright 2002-2005 INRIA - All rights reserved\n\n");
	printf("Usage: %s [options]\n", cmdName);
	printf("COMMON OPTIONS:\n");
	printf("    -h[elp]     this help\n");
	printf("    -k<n>       set number of DATA packets to n\n");
	printf("    -r<n>       set number of FEC  packets to n\n");
	printf("    -l<n>       set left degree in bipartite graph\n");
	printf("    -s<n>       sets packets size to n\n");
	exit(-1);
}



/* Parse the command line and its options */
void ParseCommandLine (int argc, char *argv[])
{
	int	c;
	char *OptList = "k:r:l:s:v:h:";

#ifdef SOLARIS
	extern char *optarg;
#elif defined(WIN32)
	char *optarg = NULL;
#endif
	if(argc < 1)
		printUsage(argv[0]);

#ifdef WIN32
	while ((c = GetOption(argc, argv, OptList, &optarg)) != 0)
#else
	while ((c = getopt(argc, argv, OptList)) != EOF)
#endif
	{
		switch (c) {
		case 'k':
			if (isdigit((int)*optarg)) {
				nbDATA = atoi(optarg);
				nbPKT = nbDATA + nbFEC;
			} else
				EXIT(("bad argument -k%s\n", optarg))
			break;

		case 'r':
			if (isdigit((int)*optarg)) {
				nbFEC = atoi(optarg);
				nbPKT = nbDATA + nbFEC;
			} else
				EXIT(("bad argument -r%s\n", optarg))
			break;

		case 'l':
			if (isdigit((int)*optarg)) {
				left_degree = atoi(optarg);
			} else
				EXIT(("bad argument -l%s\n", optarg))
			break;

		case 's':
			if (isdigit((int)*optarg)) {
				pktSize = atoi(optarg);
			} else
				EXIT(("bad argument -s%s\n", optarg))
			break;

		case 'v':
			if (isdigit((int)*optarg)) {
				verbosity = atoi(optarg);
				if (verbosity != 0 && verbosity != 1) {
					EXIT(("bad argument -v%s\n", optarg))
				}
			} else
				EXIT(("bad argument -v%s\n", optarg))
			break;

		case 'h':
			printUsage(argv[0]);
			break;

		default:
			/*
			 * NB: getopt returns '?' when finding an
			 * unknown argument; avoid the following
			 * error msg in that case
			 */
			if (c != '?')
				fprintf(stderr, "ERROR, bad argument\n");
			printUsage(argv[0]);
			break;
		}
	}
}


