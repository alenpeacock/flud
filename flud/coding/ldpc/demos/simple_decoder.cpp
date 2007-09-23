/* $Id: simple_decoder.cpp,v 1.1 2006/07/16 06:05:04 alen Exp $ */

/*  LDPC simple FEC decoder sample.
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
SOCKET initSocket( );
void DumpBuffer32( char*, int );


int main(int argc, char* argv[])
{
	// Our session object...
	LDPCFecSession MyFecSession;

	// Received (and rebuilt) packets (DATA and FEC) are stored in a 
	// packets array where each packet is an array of bytes (char).
	char**	packetsArray = NULL;

	SOCKET	mySock	= INVALID_SOCKET;
	//char*	recvPkt	= NULL;
	char*	buff	= NULL;
	int	pktSz32	= PKTSZ/4;
	int	ret	= -1;
	int	seqNo	= -1;
	int	decodeSteps = 0;

	// Sets the verbosity level
	MyFecSession.SetVerbosity(VERBOSITY);

	// Initialize the LDPC session
	if(MyFecSession.InitSession( NBDATA, NBFEC, PKTSZ, FLAG_DECODER, LEFT_DEGREE, SEED, SESSION_TYPE ) == LDPC_ERROR)
	{
		printf("Error: Unable to initialize LDPC Session\n");
		ret = -1; goto cleanup;
	}
	MyFecSession.MoreAbout(stdout);
	
	// Initialize our UDP socket
	mySock = initSocket();
	if( mySock == INVALID_SOCKET ) {
		printf("Error initializing socket\n");
		ret = -1;
		goto cleanup;
	}

	//recvPkt		= (char*) calloc(pktSz32,   sizeof(int));
	buff		= (char*) calloc(pktSz32+1, sizeof(int));
	packetsArray	= (char**)calloc(NBPKT,     sizeof(char*));
	//if ( recvPkt==NULL || buff==NULL || packetsArray==NULL ) {
	if ( buff==NULL || packetsArray==NULL ) {
		printf("Error: insufficient memory (calloc failed in main())\n");
		ret = -1; goto cleanup;
	}

	printf( "Decoding in progress...\nWaiting for new packets...\n" );
	while( !MyFecSession.IsDecodingComplete((void**)packetsArray) )
	{
		decodeSteps++;
		ret = recvfrom( mySock, buff, PKTSZ+4, 0, NULL, NULL );
		if(ret != PKTSZ+4) {
			printf("Error receiving packet!\n");
			ret = -1;
			goto cleanup;
		}
		// OK, new packet received...
		seqNo = ntohl(*(int*)buff);
		//memcpy( recvPkt, buff+4, PKTSZ);
		printf("------------------------------------\n");
		printf("--- Step %d : new packet received: %02d\n", decodeSteps, seqNo);
		// Give this new packet to FEC object (will do the needed mem alloc)
		// Fec decoder may recover some missing packets during this call
		MyFecSession.DecodeFecStep( (void**)packetsArray, (buff+4), seqNo, true  );
	}

	if (VERBOSITY > 1) // Dump the DATA to screen (if needed)
	{
		for(int i=0; i<NBDATA; i++) {
			printf("DATA[%d]= ", i);
			DumpBuffer32(packetsArray[i], pktSz32);
		}
	}

	printf("Done! All DATA packets rebuilt in %d decoding steps [%d-%d]\n", decodeSteps, NBDATA, NBPKT);

// Cleanup...
cleanup:
	if( mySock!= INVALID_SOCKET ) closesocket(mySock);
	if( MyFecSession.IsInitialized() ) MyFecSession.EndSession();

	if( packetsArray ) {
		for( int i=0; i<NBPKT; i++ ) {
			free(packetsArray[i]);
		}
		free(packetsArray);
	}
	if(buff) free(buff);
	//if(recvPkt) free(recvPkt);


	// Bye bye! :-)
	return ret;
}


/* Initialize Winsock engine and our UDP Socket */
SOCKET initSocket()
{
	SOCKET s = INVALID_SOCKET;
	int err  = SOCKET_ERROR;

#ifdef WIN32
	WORD wVersionRequested = MAKEWORD( 2, 0 );
	WSADATA wsaData;
	err = WSAStartup( wVersionRequested, &wsaData );
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

	SOCKADDR_IN bindAddr;
	bindAddr.sin_family = AF_INET;
	bindAddr.sin_port = htons((short)DEST_PORT);
	bindAddr.sin_addr.s_addr = INADDR_ANY;

	err = bind( s, (SOCKADDR*)&bindAddr, sizeof(bindAddr));
	if( err == SOCKET_ERROR)
	{
		printf("initSocket: bind() failed. Port %d may be already in use\n", DEST_PORT);
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

