/* $Id: ldpc_fec.h,v 1.1 2006/07/16 06:05:06 alen Exp $ */
/* 
 *  LDPC/LDGM FEC Library.
 *  (c) Copyright 2002-2005 INRIA - All rights reserved
 *  Main authors: Christoph Neumann (christoph.neumann@inrialpes.fr)
 *                Vincent Roca      (vincent.roca@inrialpes.fr)
 *		  Julien Laboure   (julien.laboure@inrialpes.fr)
 *
 *  This copyright notice must be retained and prominently displayed,
 *  along with a note saying that the original programs are available from
 *  Vincent Roca's web page, and note is made of any changes made to these
 *  programs.  
 *
 *  This library is free software; you can redistribute it and/or
 *  modify it under the terms of the GNU Lesser General Public
 *  License as published by the Free Software Foundation; either
 *  version 2.1 of the License, or (at your option) any later version.
 *
 *  This library is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 *  Lesser General Public License for more details.
 *
 *  You should have received a copy of the GNU Lesser General Public
 *  License along with this library; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

#ifndef LDPC_FEC
#define LDPC_FEC

#include <math.h>
#include <sys/types.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#ifndef WIN32
#include <inttypes.h>
#else
#include <STDDEF.H>
#endif

#include "ldpc_matrix_sparse.h"
#ifdef LDPC
#include "ldpc_matrix_dense.h"
#endif

#include "ldpc_create_pchk.h"
#ifdef LDPC
#include "ldpc_create_gen.h"
#endif


/* Enable/disable partial sum optimazation decoding */
//#define PART_SUM_OPTIMIZATION

/* Enable/disable external memory management support */
#define EXTERNAL_MEMORY_MGMT_SUPPORT

/**             
 * Error status returned by functions.
 */             
enum ldpc_error_status {
	LDPC_OK = 0,
	LDPC_ERROR = 1
};



/**
 * Is the session a coding or decoding session, or both.
 */
#define FLAG_CODER	0x00000001
#define FLAG_DECODER	0x00000002
#define FLAG_BOTH (FLAG_DECODER|FLAG_CODER)


/*
 * This is the LDPC FEC session class, where all the context information
 * is kept for encoding/decoding this block. To "k" source packets (A.K.A.
 * symbols), the LDPC codec can add "n-k" parity (or FEC) packets (symbols),
 * for a total of "n" packets (symbols). Source packets are numbered {0; k-1}
 * and parity packets {k; n-1}.
 * There must be one such FEC session instance per FEC block.
 *
 * WARNING: the following class contains a lot of checking code that
 * is only available in DEBUG mode (set -DDEBUG on the compiling line).
 * Whenever used with a new application, first validate your code in
 * DEBUG mode, and switch to production code only in a second step...
 */
class LDPCFecSession {
public:

/**
 * LDPCFecSession Contructor and Destructor.
 */
	LDPCFecSession ();
	~LDPCFecSession ();


/**
 * InitSession: Initializes the LDPC session.
 * @param nbDataPkt	(IN) number of DATA packets (i.e. k).
 * @param nbFecPkt	(IN) number of FEC packets (i.e. n-k).
 *			Be careful that n-k cannot be less than the left
 *			degree, otherwise an error is returned.
 * @param pktSize	(IN) packet size in bytes. MUST BE multiple of 4.
 * @param flags		(IN) session flags (FLAG_CODER, FLAG_DECODER, ...).
 * @param leftDegree	(IN) number of check edges per packet (FEC constraints).
 * @param seed		(IN) seed used to build the parity check matrix (H).
 * @param codecType	(IN) Type of codec algorithm and matrix to use.
 *			Can be on of TypeLDGM, TypeSTAIRS, TypeTRIANGLE,
 *			TypeLDPC
 * @return		Completion status (LDPC_OK or LDPC_ERROR).
 */
	ldpc_error_status InitSession  (int	nbDataPkt,
					int	nbFecPkt,
					int	pktSize,
					int	flags = FLAG_BOTH,
					int	leftDegree = 3,
					int	seed = 1,
					SessionType	codecType = TypeTRIANGLE);


/**
 * SetCallbackFunctions: Set the various callback functions for this session.
 *
 * - The DecodedPkt callback function is called each time a DATA packet
 *   is decoded by the DecodeFecStep() function. What this function does is
 *   application-dependant, but it must return a pointer to a data buffer,
 *   left uninitialized, of the appropriate size.
 *   In EXTERNAL_MEMORY_MGMT_SUPPORT mode, this function returns an opaque
 *   packet pointer. The associated buffer, where actual data will be stored,
 *   must be retrieved via the GetData callback.
 *
 * In EXTERNAL_MEMORY_MGMT_SUPPORT mode, the following callbacks are defined:
 * - The AllocTmpBuffer callback is called each time a temporary buffer is
 *   required by the system, e.g. to store a partial sum (check node). This
 *   function returns a packet pointer, and accessing the data buffer requires
 *   a call to the GetData callback. The associated data buffer MUST be 
 *   initialized to '0' by the callback.
 * - The GetData callback is called each time the data associated to a packet
 *   must be read. What this function does is application-dependant.
 * - The StoreData callback is called each time a packet's buffer has been
 *   updated and must be stored reliably by the memory mgmt system.
 *   What this function does is application-dependant.
 * - The FreePkt callback is called each time a packet (or temporary buffer)
 *   is no longer required and can be free'd by the memory mgmt system.
 *
 * All callback functions require an opaque context parameter, that is the
 * same parameter as the one given to DecodeFecStep().
 *
 * @param DecodedPkt_callback	(IN) Pointer to an application's callback.
 * 				Given the size of a newly created DATA packet
 *				and its sequence number, this function enables
 *				the callee to allocate a packet structure.
 * 				This function returns a pointer to the data
 *				buffer allocated or to the packet in
 *				EXTERNAL_MEMORY_MGMT_SUPPORT mode.
 *				This callback is never called when decoding
 *				a FEC packet!
 *
 * @param AllocTmpBuffer_callback (IN) Pointer to an application's callback.
 *				Valid in EXTERNAL_MEMORY_MGMT_SUPPORT mode.
 *				Given the desired buffer size, this function
 *				allocates a packet that will contain a buffer
 *				of appropriate size and initialized to '0'.
 *
 * @param GetData_callback	(IN) Pointer to an application's callback.
 *				Valid in EXTERNAL_MEMORY_MGMT_SUPPORT mode.
 *				Given the packet pointer, this function
 *				returns the data buffer, after making sure
 *				that this latter is available and up-to-date.
 *
 * @param GetDataPtrOnly_callback (IN) Pointer to an application's callback.
 *				Valid in EXTERNAL_MEMORY_MGMT_SUPPORT mode.
 *				Same as GetData_callback, except that no
 *				check is made to make sure data is available
 *				and up-to-date. It makes sense when buffer
 *				has just been allocated before, for instance
 *				because this is a destination buffer in a
 *				memcpy() syscall.
 *
 * @param StoreData_callback	(IN) Pointer to an application's callback.
 *				Valid in EXTERNAL_MEMORY_MGMT_SUPPORT mode.
 *				Given the packet pointer, this function stores
 *				data reliably in the memory mgmt system.
 *
 * @param FreePkt_callback	(IN) Pointer to an application's callback.
 *				Valid in EXTERNAL_MEMORY_MGMT_SUPPORT mode.
 *				This function will be called with a packet
 *				pointer, so that the external memory mgmt
 *				system can free the associated buffer.
 *
 * @param context_4_callback (IN) Pointer to context that will be passed
 * 				to the callback function (if any). This
 * 				context is not interpreted by this function.
 *
 * @return			Completion status (LDPC_OK or LDPC_ERROR).
 */
	ldpc_error_status SetCallbackFunctions (
		void* (*DecodedPkt_callback)	(void	*context,
						 int	size,
						 int	pkt_seqno),
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
		void* (*AllocTmpBuffer_callback)(void	*context,
						 int	size),
		void* (*GetData_callback)	(void	*context,
						 void	*pkt),
		void* (*GetDataPtrOnly_callback)(void	*context,
						 void	*pkt),
		ldpc_error_status (*StoreData_callback)
						(void	*context,
						 void	*pkt),
		ldpc_error_status (*FreePkt_callback)
						(void	*context,
						 void	*pkt),
#endif /* EXTERNAL_MEMORY_MGMT_SUPPORT */
		void*	context_4_callback = NULL);


/**
 * EndSession: Ends the LDPC session, cleans up everything.
 */
	void EndSession ();


/**
 * IsInitialized: Check if the LDPC session has been initialized.
 * @return	  TRUE if the session is ready and initialized, FALSE if not.
 */
	bool IsInitialized ();


/**
 * Set the verbosity level.
 * @param verb		(IN) new verbosity level (0: no trace, 1: all traces)
 */
	void SetVerbosity (int	verb);


/**
 * Prints version number and copyright information about this codec.
 * @param out		(IN) FILE handle where the string should be written.
 */
	void MoreAbout (FILE	*out);


/**
 * Build a new FEC packet.
 * @param pkt_canvas	(IN)	Array of source DATA and FEC packets.
 *				This is a table of n pointers to buffers
 *				containing the source and FEC packets.
 * @param fec_index	(IN)	Index of FEC packet to build in {0.. n-k-1}
 *				range (!)
 * @param fec_pkt	(IN-OUT) Pointer to the FEC packet buffer that will
 *				be built. This buffer MUST BE allocated
 *				before,	but NOT cleared (memset(0)) since
 *				this function will do it.
 * @return			Completion status (LDPC_OK or LDPC_ERROR).
 */
	ldpc_error_status BuildFecPacket (void*		pkt_canvas[],
					  int		fec_index,
					  void*		fec_pkt); 


/**
 * Build a new FEC packet.
 * @param pkt_canvas	(IN)	Array of source DATA and FEC packets.
 *				This is a table of n pointers to buffers
 *				containing the source and FEC packets.
 * @param pkt_index	(IN)	Index of column/packet.
 * @param built_parity_pkts (OUT)
 * @param nb_built_parity_pkts (OUT)
 * @return			Completion status (LDPC_OK or LDPC_ERROR).
 */
	ldpc_error_status BuildFecPacketsPerCol (void*	pkt_canvas[],
						 int	pkt_index,
						 int*	(*built_parity_pkts),
						 int*	nb_built_parity_pkts); 


/**
 * Perform a new decoding step thanks to the newly received packet.
 * @param pkt_canvas	(IN-OUT) Global array of received or rebuilt source
 * 				packets (FEC packets need not be stored here).
 *				This is a table of k pointers to buffers.
 * 				This array must be cleared (memset(0)) upon
 * 				the first call to this function. It will be
 * 				automatically updated, with pointers to
 * 				packets received or decoded, by this function.
 * @param new_pkt	(IN)	Pointer to the buffer containing the new packet.
 * @param new_pkt_seqno	(IN)	New packet's sequence number in {0.. n-1} range.
 * @param store_packet	(IN)	true if the function needs to allocate memory,
 *				copy the packet content in it, and call
 *				any required callback.
 *				This is typically done when this function is
 *				called recursively, for newly decoded packets,
 *				or under special circunstances (e.g. perftool).
 * @return			Completion status (LDPC_OK or LDPC_ERROR).
 */
	ldpc_error_status DecodeFecStep (void*	pkt_canvas[],
					 void*	new_pkt,
					 int	new_pkt_seqno,
					 bool	store_packet);


/**
 * Perform a new decoding step thanks to the newly received packet.
 * Same as the other DecodeFecStep method, without the store_packet argument
 * (prefered solution).
 * @param pkt_canvas	(IN-OUT) Global array of received or rebuilt source
 * 				packets (FEC packets need not be stored here).
 *				This is a table of k pointers to buffers.
 * 				This array must be cleared (memset(0)) upon
 * 				the first call to this function. It will be
 * 				automatically updated, with pointers to
 * 				packets received or decoded, by this function.
 * @param new_pkt	(IN)	Pointer to the buffer containing the new packet.
 * @param new_pkt_seqno	(IN)	New packet's sequence number in {0.. n-1} range.
 * @return			Completion status (LDPC_OK or LDPC_ERROR).
 
 */
 
	ldpc_error_status DecodeFecStep (void*	pkt_canvas[],
					 void*	new_pkt,
					 int	new_pkt_seqno);


/**
 * PacketAlreadyKnown: Returns true if the packet has already been received
 * or decoded (i.e. if it is already known), false otherwise.
 * @param pkt_canvas	(IN)	Array of received/rebuilt source packets.
 * @param new_pkt_seqno	(IN)	New packet's sequence number in {0.. n-1} range.
 * @return			TRUE if this packet has already been received
 * 				or decoded.
 */
	bool PacketAlreadyKnown (void*	pkt_canvas[],
				 int	new_pkt_seqno);


/**
 * IsDecodingComplete: Checks if all DATA packets have been received/rebuilt.
 * @param pkt_canvas	(IN)	Array of received/rebuilt source packets.
 * @return			TRUE if all DATA packets have been received
 * 				or decoded.
 */
	bool IsDecodingComplete (void*	pkt_canvas[] );


/****** PRIVATE MEMBERS ******************************************************/
private:

	/**
	 * Return true if this is a DATA source packet.
	 * @param pktSeqno	(IN) packet sequence number in {O; n-1} range
         * @return		true if DATA packet, false if parity packet
	 */
	bool	IsDataPkt	(int	pktSeqno);

	/**
	 * Return true if this is a parity (AKA FEC) packet.
	 * @param pktSeqno	(IN) packet sequence number in {O; n-1} range
         * @return		true if parity packet, false if parity packet
	 */
	bool	IsParityPkt	(int	pktSeqno);

	/**
	 * Packet sequence number to column index translation.
	 * @param pktSeqno	(IN) packet sequence number in {O; n-1} range
         * @return		corresponding column number in matrix
	 */
	int	GetMatrixCol	(int pktSeqno);

	/**
	 * Internal column index to packet sequence number translation.
	 * @param matrixCol	(IN) column number in matrix
	 * @return		corresponding packet sequence number in
	 *			{O; n-1} range
	 */
	int	GetPktSeqno	(int matrixCol);

	/**
	 * Get the data buffer associated to a packet stored in the
	 * pkt_canvas[] / m_parity_pkt_canvas[] / m_checkValues[] tables.
	 * This function is usefull in EXTERNAL_MEMORY_MGMT_SUPPORT mode
	 * when a the Alloc/Get/Store/Free callbacks are used, but it does
	 * nothing in other mode. This is due to the fact that with these
	 * callbacks, the various canvas do not point to data buffers but
	 * to intermediate structures, and therefore accessing the associated
	 * buffer needs extra processing.
	 * @param pkt		(IN) pointer stored in the various canvas
	 * @return		associated buffer
	 */
	void	*GetBuffer	(void	*pkt);

	/**
	 * Same as GetBuffer, except that is call does not use the
	 * GetData_callback but on GetDataPtrOnly_callback.
	 * For instance, in EXTERNAL_MEMORY_MGMT_SUPPORT, it will not
	 * make sure that data is actually available and up-to-date,
	 * perhaps because this is a destination buffer in a memcpy
	 * that has just been allocated!
	 * @param pkt		(IN) pointer stored in the various canvas
	 * @return		associated buffer
	 */
	void	*GetBufferPtrOnly	(void	*pkt);

	/**
	 * Calculates the XOR sum of two packets: to = to + from.
	 * @param to		(IN/OUT) source packet
	 * @param from		(IN/OUT) packet added to the source packet
	 */
	void	AddToPacket	(void	*to,
				 void	*from);

	bool	m_initialized;	// is TRUE if session has been initialized
	int	m_sessionFlags;	// Mask containing session flags
				// (FLAG_CODER, FLAG_DECODER, ...)
	SessionType	m_sessionType;	// Type of the session. Can be one of
					// LDPC, LDGM, LDGM STAIRS, and
					// LDGM TRIANGLE.
	int	m_verbosity;	// verbosity level:	0 means no trace
				//			1 means infos
				//			2 means debug

	unsigned int	m_pktSize;	// Size of packets in BYTES
#if defined (__LP64__) || (__WORDSIZE == 64)
	unsigned int	m_pktSize64;	// Size of packets in 64bits unit
					// (m_PktSize64 = floor(m_PktSize/8.0))
					// we use floor since packet size
					// can be a multiple of 32 bits.
#endif
	unsigned int	m_pktSize32;	// Size of packets in 32bits unit
					// (m_PktSize32 = m_PktSize/4)

	int	m_nbDataPkt;	// number fo DATA packets (K)
	int	m_nbFecPkt;	// number of FEC packets (=m_nbCheck)
#	define	m_nbCheck m_nbFecPkt
#	define m_nbTotalPkt (m_nbFecPkt+m_nbDataPkt)

	mod2sparse*	m_pchkMatrix;	// Parity Check matrix in sparse mode 
					// format. This matrix is also used as
					// a generator matrix in LDGM-* modes.
#ifdef LDPC
	mod2dense*	m_genMatrix;	// Generator matrix (used in LDPC mode).
	int*		m_columnsOrder;	// Array: Columns order (after H
					// reordering).
	int*		m_columnsIndex;	// Array: Columns index (after H
					// reordering).
#endif

	int		m_leftDegree;	// Number of equations per data packet

	// Encoder specific...
	int*		m_nb_unknown_pkts_encoder; // Array: nb unknown pkts per
					// check node. Used during per column
					// encoding.

	// Decoder specific...
	void**		m_checkValues;	// Array: current check-nodes value.
					// Each entry is the sum (XOR) of some
					// or all of the known packets in this
					// equation.
	int*		m_nbPkts_in_equ;// Array: nb of variables per check
					// node, ie. per equation
	int		m_firstNonDecoded; // index of first pkt not decoded.
					// Used to know whether decoding is
					// finished or not.
	int*		m_nb_unknown_pkts; // Array: nb unknown pkts per check node
	int*		m_nbEqu_for_parity; // Array: nb of equations where
					// each parity packet is included
	void**		m_parity_pkt_canvas; //Canvas of stored parity packets.

#if 0
	uintptr_t* 	m_builtPkt; 	// Packet built by decoder, used for 
					// recursive calls of DecodeFecStep
#endif
	bool		m_triangleWithSmallFECRatio;
					// with LDGM Triangle and a small FEC
					// ratio (ie. < 2), some specific
					// behaviors are needed...

	// Callbacks
	void* (*m_decodedPkt_callback) (void* context, int size, int pkt_seqno);
					// Function called each time a new
					// source packet is decoded.
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
	void* (*m_allocTmpBuffer_callback)(void *context, int size);
					// Function called each time a
					// temporary buffer is required
	void* (*m_getData_callback)	(void *context, void *pkt);
					// Function called each time the data
					// associated to a packet must be read
	void* (*m_getDataPtrOnly_callback) (void *context, void *pkt);
					// Function called each time we need
					// a ptr to the data buffer associated
					// to a packet
	ldpc_error_status (*m_storeData_callback) (void *context, void *pkt);
					// Function called each time a packet's
					// buffer has been updated and must be
					// stored reliably
	ldpc_error_status (*m_freePkt_callback) (void *context, void *pkt);
					// Function called each time a packet
					// (or tmp buffer) can be free'd
#endif /* EXTERNAL_MEMORY_MGMT_SUPPORT */
	void*		m_context_4_callback; // used by callback functions
};


//------------------------------------------------------------------------------
// Inlines for all classes follow
//------------------------------------------------------------------------------

inline bool
LDPCFecSession::IsInitialized( )
{
	return m_initialized;
}

inline bool
LDPCFecSession::IsDataPkt	(int	pktSeqno)
{
	return ((pktSeqno < m_nbDataPkt) ? true : false);
}

inline bool	
LDPCFecSession::IsParityPkt	(int	pktSeqno)
{
	return ((pktSeqno < m_nbDataPkt) ? false : true);
}

#ifndef DEBUG
inline void*
LDPCFecSession::GetBuffer	(void	*pkt)
{
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
	if (m_getData_callback) {
		return (m_getData_callback(m_context_4_callback, pkt));
	} else
#endif
		return pkt;		// nothing to do here
}

inline void*
LDPCFecSession::GetBufferPtrOnly	(void	*pkt)
{
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
	if (m_getDataPtrOnly_callback) {
		return (m_getDataPtrOnly_callback(m_context_4_callback, pkt));
	} else
#endif
		return pkt;		// nothing to do here
}
#endif

#endif
