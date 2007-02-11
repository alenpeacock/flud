/* $Id: simple_coder.cpp,v 1.1 2006/07/16 06:05:04 alen Exp $ */

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


#include "simple_coder.h"


/* Prototypes */
SOCKET	initSocket( void );
void	randomizeArray( int**, int );
void	DumpBuffer32( char*, int );



int main(int argc, char* argv[])
{
	// Our session object...
	LDPCFecSession MyFecSession;

	// Original packets (DATA and FEC) are stored in a packets array
	// where each packet is an array of bytes (char)
	char**	packetsArray	= NULL;

	SOCKET	mySock		= INVALID_SOCKET;
	int*	randOrder	= NULL;
	int	pktSz32		= PKTSZ/4;
	int	ret		= -1;
	int	i		= 0;

	// Sets the verbosity level
	MyFecSession.SetVerbosity(VERBOSITY);

	// Initialize the LDPC session
	if(MyFecSession.InitSession( NBDATA, NBFEC, PKTSZ, FLAG_CODER, LEFT_DEGREE, SEED, SESSION_TYPE ) == LDPC_ERROR)
	{
		printf("Error: Unable to initialize LDPC Session\n");
		ret = -1; goto cleanup;
	}
	MyFecSession.MoreAbout(stdout);
	
	// Let's alloc our fictive DATA Packets...
	printf("\nFilling DATA Packets...\n");
	packetsArray = (char**)calloc( NBPKT, sizeof(char*) );
	if( packetsArray == NULL ) {
		printf("Error: insufficient memory (calloc failed for packetsArray)\n");
		ret = -1; goto cleanup;
	}

	for( i=0; i<NBDATA; i++ )
	{	// First packet filled with 0x1111..., second with 0x2222..., etc.
		packetsArray[i] = (char*) calloc(pktSz32, sizeof(int));
		if( packetsArray[i] == NULL ) {
			printf("Error: insufficient memory (calloc failed for packetsArray[%d])\n", i);
			ret = -1; goto cleanup;
		}
		memset( packetsArray[i], (char)(i+1), PKTSZ );
		if (VERBOSITY > 1)	// dump packet to screen (if wanted)
		{
			printf( "DATA[%03d]= ", i );
			DumpBuffer32( packetsArray[i], pktSz32 );
		}
	}

	// Now creating some FEC Packets...
	printf("\nCreating FEC Packets...\n");

	for( i=0; i < NBFEC; i++ )
	{
		packetsArray[i+NBDATA] = (char*)calloc(pktSz32, sizeof(int));
		if( packetsArray[i+NBDATA] == NULL ) {
			printf("Error: insufficient memory (calloc failed for packetsArray[%d])\n", i+NBDATA);
			ret = -1; goto cleanup;
		}
		MyFecSession.BuildFecPacket( (void**)packetsArray, i, packetsArray[i+NBDATA] );
		if (VERBOSITY > 1)	// dump packet to screen (if wanted)
		{
			printf( "DATA[%03d]= ", i+NBDATA );
			DumpBuffer32( packetsArray[i+NBDATA], pktSz32 );  // dump packet to screen
		}
	}

	// Randomize packets order...
	printf("\nRandomizing transmit order...\n");
	randOrder = (int*)calloc( NBPKT, sizeof(int) );
	if( randOrder == NULL ) {
		printf( "Error: insufficient memory (calloc failed for randOrder)\n" );
		ret = -1; goto cleanup;
	}
	randomizeArray( &randOrder, NBPKT );
	
	// ... and finally, throw our packets to space using UDP socket :-)
	char pktWithHeader[PKTSZ+4];
	SOCKADDR_IN destHost;
	destHost.sin_family = AF_INET;
	destHost.sin_port = htons((short)DEST_PORT);
	destHost.sin_addr.s_addr = inet_addr(DEST_IP);
	mySock = initSocket();
	if( mySock == INVALID_SOCKET )
	{
		printf( "main: Error initializing socket!\n" );
		ret = -1; goto cleanup;
	}
	printf( "Sending packets (DATA&FEC) to %s/%d\n", DEST_IP, DEST_PORT );
	for( i=0; i < NBPKT; i++ )
	{
		// Adding pkt header (wich only countains a 32bits sequence number)
		*((int*)pktWithHeader) = htonl(randOrder[i]);
		memcpy(pktWithHeader+4, packetsArray[randOrder[i]], PKTSZ);

		printf("%05d=> Sending packet %-5d (%s)\n", i+1, randOrder[i], randOrder[i]<NBDATA ? "DATA" : "FEC");
		ret = sendto(mySock, pktWithHeader, PKTSZ+4, 0, (SOCKADDR *)&destHost, sizeof(destHost));
		if (ret == SOCKET_ERROR) {
			printf( "main: Error! sendto() failed!\n" );
			ret = -1;
			break;
		}
		SLEEP(10); // SLEEP avoid UDP flood (in milliseconds)
	}
	if( i==NBPKT ) {
		printf( "\nComplete! %d packets sent successfully.\n", i);
		ret = 1;
	}
	

cleanup:
	// Cleanup...
	if( mySock!= INVALID_SOCKET ) closesocket(mySock);
	if( MyFecSession.IsInitialized() ) MyFecSession.EndSession();
	if( randOrder ) { free(randOrder); }

	if( packetsArray ) {
		for( i=0; i<NBPKT; i++ ) {
			free(packetsArray[i]);
		}
		free(packetsArray);
	}

	// Bye bye! :-)
	return ret;
}



// Randomize an array of integers
void randomizeArray( int** array, int arrayLen )
{
	int backup=0,randInd=0;
	int	seed;	/* random seed for the srand() function */

#ifdef WIN32
	seed = timeGetTime();
#else  /* UNIX */
	struct timeval	tv;
	if (gettimeofday(&tv, NULL) < 0) {
		perror("randomizeArray: gettimeofday() failed:");
		exit(-1);
	}
	seed = (int)tv.tv_usec;
#endif /* OS */
	srand(seed);
	for( int i=0; i<arrayLen; i++ )
		(*array)[i]=i;

	for( int i=0; i<arrayLen; i++ )
	{
		backup = (*array)[i];
		randInd = rand()%arrayLen;
		(*array)[i] = (*array)[randInd];
		(*array)[randInd] = backup;
	}
}



/* Initialize Winsock engine and our UDP Socket */
SOCKET initSocket()
{
	SOCKET s;

#ifdef WIN32
	WORD wVersionRequested = MAKEWORD( 2, 0 );
	WSADATA wsaData;
	int err = WSAStartup( wVersionRequested, &wsaData );
	if ( err != 0 )
	{
		printf( "Error: unable to Initialize Winsock engine\n" );
		return INVALID_SOCKET;
	}
#endif
	s = socket(AF_INET, SOCK_DGRAM, 0);
	if (s == INVALID_SOCKET)
	{
		printf("Error: call to socket() failed\n");
		return INVALID_SOCKET;
	}
	return s;
}



void DumpBuffer32( char* buf, int len32 )
{
	int *ptr; int j = 0;

	printf("0x");
	for (ptr = (int*)buf; len32 > 0; len32--, ptr++) {
		/* convert to big endian format to be sure of byte order */
		printf( "%08X", htonl(*ptr));
		if (++j == 10)
		{
			j = 0;
			printf("\n");
		}
	}
	printf("\n");
}

