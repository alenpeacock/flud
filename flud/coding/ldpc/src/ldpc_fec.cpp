/* $Id: ldpc_fec.cpp,v 1.1 2006/07/16 06:05:06 alen Exp $ */
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


#include "ldpc_fec.h"
#include "macros.h"
#ifdef WIN32
#include <conio.h>
#endif

/******************************************************************************
 * LDPCFecSession Contructor.
 */
LDPCFecSession::LDPCFecSession()
{
	memset(this, 0, sizeof(*this));
}


/******************************************************************************
 * LDPCFecSession Destructor.
 */
LDPCFecSession::~LDPCFecSession()
{
        EndSession();
}


/******************************************************************************
 * InitSession : Initializes the LDPC session.
 * => See header file for more informations.
 */
ldpc_error_status
LDPCFecSession::InitSession (	int nbDataPkt,
				int nbFecPkt,
				int pktSize,
				int flags,
				int leftDegree,
				int seed,
				SessionType codecType)
{
	mod2entry	*e;

	m_initialized	= false;
	m_sessionFlags	= flags;
	m_sessionType	= codecType;
	m_pktSize	= pktSize;
	if ((pktSize % 4) != 0) {
		fprintf(stderr, "LDPCFecSession::InitSession: ERROR: Packet size (%d bytes) IS NOT multiple of 4\n", pktSize);
		return LDPC_ERROR;
	}
#if defined (__LP64__) || (__WORDSIZE == 64)
	// pktSize is not necessarily a multiple of 8, but >> 3 will divide
	// it by 8 and keep the integral part automatically.
	m_pktSize64	= pktSize >> 3;
#endif 
	m_pktSize32	= pktSize >> 2;

	m_nbDataPkt	= nbDataPkt;
	m_nbFecPkt	= nbFecPkt;
	m_leftDegree	= leftDegree;
	m_firstNonDecoded = 0;

	if (this->m_verbosity >= 1) {
		if (m_sessionType == TypeLDGM) {
			printf("Initializing LDGM FEC Session...\n - DATA packets = %d\n - FEC packets = %d\n - Packets size = %d\n - Edges per DATA pkt = %d\n", m_nbDataPkt, m_nbCheck, m_pktSize, m_leftDegree = leftDegree);
		} else if (m_sessionType == TypeSTAIRS) {
			printf("Initializing LDGM STAIRCASE FEC Session...\n - DATA packets = %d\n - FEC packets = %d\n - Packets size = %d\n - Edges per DATA pkt = %d\n", m_nbDataPkt, m_nbCheck, m_pktSize, m_leftDegree = leftDegree);
		} else if (m_sessionType == TypeTRIANGLE) {
			printf("Initializing LDGM TRIANGLE FEC Session...\n - DATA packets = %d\n - FEC packets = %d\n - Packets size = %d\n - Edges per DATA pkt = %d\n", m_nbDataPkt, m_nbCheck, m_pktSize, m_leftDegree = leftDegree);
		} 
#ifdef LDPC
		else if (m_sessionType == TypeLDPC) {
			printf("Initializing LDPC FEC Session...\n - DATA packets = %d\n - FEC packets = %d\n - Packets size = %d\n - Edges per DATA pkt = %d\n", m_nbDataPkt, m_nbCheck, m_pktSize, m_leftDegree = leftDegree);
		}
#endif
	}

	// generate parity check matrix... 
	if (this->m_verbosity >= 1) {
		printf("Generating Parity Check Matrix (H)...");
	}
	m_pchkMatrix = CreatePchkMatrix(m_nbCheck, m_nbDataPkt + m_nbFecPkt, Evenboth, m_leftDegree, seed, false, m_sessionType, this->m_verbosity);
	if (m_pchkMatrix == NULL) {
		fprintf(stderr, "LDPCFecSession::InitSession: ERROR: call to CreatePchkMatrix failed!\n");
		return LDPC_ERROR;
	}
	if (this->m_verbosity >= 1) {
		printf("Done!\n");
	}

#ifdef LDPC
	if (m_sessionType == TypeLDPC) {
		m_columnsOrder = (int*)calloc(m_nbTotalPkt, sizeof(int));
		if (m_columnsOrder == NULL) {
			fprintf(stderr, "LDPCFecSession::InitSession: ERROR: call to calloc failed for m_columnsOrder!\n");
			return LDPC_ERROR;
		}
		if (this->m_verbosity >= 1) {
			printf("Generating Generator Matrix (G)...");
		}

		m_genMatrix = CreateGenMatrix(m_pchkMatrix, m_columnsOrder);

		m_columnsIndex = (int*)calloc(m_nbTotalPkt, sizeof(int));
		if (m_columnsIndex == NULL) {
			fprintf(stderr, "LDPCFecSession::InitSession: ERROR: call to calloc failed for m_columnsIndex!\n");
			return LDPC_ERROR;
		}
		for (int i = 0; i < m_nbTotalPkt; i++) {
			m_columnsIndex[m_columnsOrder[i]] = i;
		}

		if (this->m_verbosity >= 1) {
			printf("Done!\n");
		}

		if (this->m_verbosity >= 2) {
			printf("\n");
			for (int i = 0; i < m_nbTotalPkt; i++) {
				printf("%d ", m_columnsOrder[i]);
			}
			printf("\n\nGen Matrix:\n");
			mod2dense_print(stdout, m_genMatrix);
			printf("\n");
		}
	}
#endif

	if (m_sessionFlags & FLAG_CODER) {
		m_nb_unknown_pkts_encoder = (int*)calloc(m_nbCheck, sizeof(int));
		if (m_nb_unknown_pkts_encoder == NULL) {
			fprintf(stderr, "LDPCFecSession::InitSession: ERROR: call to calloc failed for m_nb_unknown_pkts_encoder!\n");
			return LDPC_ERROR;
		}

		for (int row=0; row<m_nbCheck; row++) {
			mod2entry *e;
			for (e = mod2sparse_first_in_row(m_pchkMatrix, row);
			     !mod2sparse_at_end(e);
			     e = mod2sparse_next_in_row(e))
			{
				m_nb_unknown_pkts_encoder[row]++;
			}
		}
	} else {
		m_nb_unknown_pkts_encoder = NULL;
	}

	if (m_sessionFlags & FLAG_DECODER) {
		// allocate all internal tables
		if (((m_checkValues	= (void**)calloc(m_nbCheck, sizeof(void*))) == NULL) ||
		    ((m_nbPkts_in_equ = (int*)calloc(m_nbCheck, sizeof(int))) == NULL) ||
		    ((m_nb_unknown_pkts = (int*)calloc(m_nbCheck, sizeof(int))) == NULL) ||
		    ((m_nbEqu_for_parity = (int*)calloc(m_nbCheck, sizeof(int))) == NULL) ||
		    ((m_parity_pkt_canvas = (void**)calloc(m_nbCheck, sizeof(void*))) == NULL)) {
			fprintf(stderr, "LDPCFecSession::InitSession: ERROR: call to calloc failed for m_parity_pkt_canvas!\n");
			return LDPC_ERROR;
		}
		// and update the various tables now
		for (int row = 0; row < m_nbCheck; row++) {
			for (e = mod2sparse_first_in_row(m_pchkMatrix, row);
			     !mod2sparse_at_end(e);
			     e = mod2sparse_next_in_row(e))
			{
				m_nbPkts_in_equ[row]++;
				m_nb_unknown_pkts[row]++;
			}
		}
		for (int seq = m_nbDataPkt; seq < m_nbTotalPkt; seq++) {
			for (e = mod2sparse_first_in_col(m_pchkMatrix,
						    GetMatrixCol(seq));
			     !mod2sparse_at_end(e);
			     e = mod2sparse_next_in_col(e))
			{
				m_nbEqu_for_parity[seq - m_nbDataPkt]++;
			}
		}
	} else {
		// CODER session
		m_checkValues = NULL;
		m_nbPkts_in_equ = NULL;
		m_nb_unknown_pkts = NULL;
		m_nbEqu_for_parity = NULL;
		m_parity_pkt_canvas = NULL;
	}
	if ((m_sessionType == TypeTRIANGLE) && ((m_nbTotalPkt/m_nbDataPkt) < 2.0)) {
		m_triangleWithSmallFECRatio = true;
	} else {
		m_triangleWithSmallFECRatio = false;
	}
#ifdef DEBUG
	if (this->m_verbosity >= 2) {
		printf("Pchk Matrix:\n");
		mod2sparse_print(stdout, m_pchkMatrix);
	}
#endif
	m_initialized = true;
	//printf("Pchk Matrix:\n");
	//mod2sparse_print(stdout, m_pchkMatrix);
	return LDPC_OK;
}


/******************************************************************************
 * SetDecodedPktCallback: Call the function whenever BuildFecPacket decodes
 * a new FEC or data packet.
 * => See header file for more informations.
 */
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
ldpc_error_status
LDPCFecSession::SetCallbackFunctions (
		void* (*DecodedPkt_callback)		(void *context, int size,
							 int pkt_seqno),
		void* (*AllocTmpBuffer_callback)	(void *context, int size),
		void* (*GetData_callback)		(void *context, void *pkt),
		void* (*GetDataPtrOnly_callback)	(void *context, void *pkt),
		ldpc_error_status (*StoreData_callback) (void *context, void *pkt),
		ldpc_error_status (*FreePkt_callback)	(void *context, void *pkt),
		void*	context_4_callback)
{
	// sanity checks first
	if (DecodedPkt_callback) {
		if (!(m_sessionFlags & FLAG_DECODER)) {
			fprintf(stderr, "LDPCFecSession::SetCallbackFunctions: ERROR: specifying DecodedPkt_callback is only valid in DECODER mode\n");
			return LDPC_ERROR;
		}
	}
	if (AllocTmpBuffer_callback) {
		if (!(m_sessionFlags & FLAG_DECODER)) {
			fprintf(stderr, "LDPCFecSession::SetCallbackFunctions: ERROR: specifying AllocTmpBuffer_callback is only valid in DECODER mode\n");
			return LDPC_ERROR;
		}
	}
	if (FreePkt_callback) {
		if (!(m_sessionFlags & FLAG_DECODER)) {
			fprintf(stderr, "LDPCFecSession::SetCallbackFunctions: ERROR: specifying FreePkt_callback is only valid in DECODER mode\n");
			return LDPC_ERROR;
		}
	}
	// then remember everything
	m_decodedPkt_callback = DecodedPkt_callback;
	m_allocTmpBuffer_callback = AllocTmpBuffer_callback;
	m_getData_callback = GetData_callback;
	m_getDataPtrOnly_callback = GetDataPtrOnly_callback;
	m_storeData_callback = StoreData_callback;
	m_freePkt_callback = FreePkt_callback;
	m_context_4_callback = context_4_callback;
	return LDPC_OK;
}

#else  /* !EXTERNAL_MEMORY_MGMT_SUPPORT */

ldpc_error_status
LDPCFecSession::SetCallbackFunctions (
		void* (*DecodedPkt_callback)	(void *context, int size, int pkt_seqno),
		void*	context_4_callback)
{
	// sanity checks first
	if (DecodedPkt_callback) {
		if (!(m_sessionFlags & FLAG_DECODER)) {
			fprintf(stderr, "LDPCFecSession::SetCallbackFunctions: ERROR: specifying DecodedPkt_callback is only valid in DECODER mode\n");
			return LDPC_ERROR;
		}
	}
	// then remember everything
	m_decodedPkt_callback = DecodedPkt_callback;
	m_context_4_callback = context_4_callback;
	return LDPC_OK;
}
#endif /* !EXTERNAL_MEMORY_MGMT_SUPPORT */


/******************************************************************************
 * EndSession : Ends the LDPC session, and cleans up everything.
 * => See header file for more informations.
 */
void
LDPCFecSession::EndSession()
{
	if (m_initialized) {
		//m_initialized = false;
		mod2sparse_free(m_pchkMatrix);
		free(m_pchkMatrix);	/* mod2sparse_free does not free it! */
#ifdef LDPC		
		if (m_sessionType == TypeLDPC) {
			mod2dense_free(m_genMatrix);
			if (m_columnsOrder) {
				free(m_columnsOrder);
			}
			if (m_columnsIndex) {
				free(m_columnsIndex);
			}
		}
#endif
		if (m_checkValues != NULL) {
			for (int i = 0; i < m_nbCheck; i++) {
				if (m_checkValues[i] != NULL) {
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
					if (m_freePkt_callback != NULL) {
						m_freePkt_callback(m_context_4_callback,
								   m_checkValues[i]);
					} else
#endif
					{
						free(m_checkValues[i]);
					}
				}
			}
			free(m_checkValues);
		}
		if (m_parity_pkt_canvas != NULL) {
			for (int i = 0; i < m_nbCheck; i++) {
				if (m_parity_pkt_canvas[i] != NULL) {
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
					if (m_freePkt_callback != NULL) {
						m_freePkt_callback(m_context_4_callback,
								   m_parity_pkt_canvas[i]);
					} else
#endif
					{
						free(m_parity_pkt_canvas[i]);
					}
				}
			}
			free(m_parity_pkt_canvas);
		}
		if (m_nbPkts_in_equ) {
			free(m_nbPkts_in_equ);
		}
		if (m_nbEqu_for_parity) {
			free(m_nbEqu_for_parity);
		}
		if (m_nb_unknown_pkts) {
			free(m_nb_unknown_pkts);
		}
		if (m_nb_unknown_pkts_encoder) {
			free(m_nb_unknown_pkts_encoder);
		}
	}
	// and now init everything!
	memset(this, 0, sizeof(*this));
}


/******************************************************************************
 * SetVerbosity: Sets the verbosity level.
 * => See header file for more informations.
 */
void
LDPCFecSession::SetVerbosity(int	verb)
{
	this->m_verbosity = verb;
}


/******************************************************************************
 * MoreAbout:Prints version number and copyright information about this codec.
 * => See header file for more informations.
 */
void
LDPCFecSession::MoreAbout (FILE		*out)
{
	fprintf(out, "LDPC/LDGM large block FEC codec - Version 1.8-pre, May 25th, 2005\n");
	fprintf(out, "  Copyright (c) 2002-2005 INRIA - All rights reserved\n");
	fprintf(out, "  Authors: C. Neumann, V. Roca, J. Laboure\n");
	fprintf(out, "  This codec contains code from R. Neal:\n");
	fprintf(out, "  Copyright (c) 1995-2003 by Radford M. Neal\n");
	fprintf(out, "  See the associated LICENCE.TXT file for licence information\n");
	switch (m_sessionType) {
	case TypeLDGM:
		fprintf(out, "  LDPC/LDGM codec mode\n");
		break;
	case TypeSTAIRS:
		fprintf(out, "  LDPC/LDGM Staircase codec mode\n");
		break;
	case TypeTRIANGLE:
		fprintf(out, "  LDPC/LDGM Triangle codec mode\n");
		break;
#ifdef LDPC
	case TypeLDPC:
		fprintf(out, "  LDPC codec mode\n");
		break;
#endif
	}
}


#ifdef DEBUG
/******************************************************************************
 * Debug is simpler when this is not an inline function.
 * => See header file for more informations.
 */
void*
LDPCFecSession::GetBuffer	(void	*pkt)
{
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
	if (m_getData_callback) {
		return (m_getData_callback(m_context_4_callback, pkt));
	} else
#endif
		return pkt;		// nothing to do here
}


/******************************************************************************
 * Debug is simpler when this is not an inline function.
 * => See header file for more informations.
 */
void*
LDPCFecSession::GetBufferPtrOnly	(void	*pkt)
{
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
	if (m_getDataPtrOnly_callback) {
		return (m_getDataPtrOnly_callback(m_context_4_callback, pkt));
	} else
#endif
		return pkt;		// nothing to do here
}
#endif /* DEBUG */


/******************************************************************************
 * Calculates the XOR sum of two packets: to = to + from.
 * => See header file for more informations.
 */
void
LDPCFecSession::AddToPacket	(void	*to,
				void	*from)
{
	uintptr_t	offset;			
#if defined (__LP64__) || (__WORDSIZE == 64)
	// 64-bit machines
	for (offset = 0; offset < m_pktSize64; offset++) {
		*(((uintptr_t*)to) + offset) ^= *(((uintptr_t*)from) + offset);
	}
	/* add the last 32 bits if needed */
	if ((m_pktSize64 << 1) < m_pktSize32) {
		*(uint32_t*)(((uintptr_t*)to) + offset) ^= *(uint32_t*)(((uintptr_t*)from) + offset);
	}

#else

	// 32-bit machines
	for (offset = 0; offset < m_pktSize32; offset++) {
		*(((uintptr_t*)to) + offset) ^=  *(((uintptr_t*)from) + offset);
	}
#endif
}


/******************************************************************************
 * BuildFecPacket: Builds a new FEC packet.
 * => See header file for more informations.
 */
ldpc_error_status
LDPCFecSession::BuildFecPacket (void* pkt_canvas[],
				int fec_index,
				void* fec_pkt)
{
	uintptr_t	*fec_buf;	// buffer for this FEC packet
	uintptr_t	*to_add_buf;	// buffer for the  data/FEC pkt to add
        mod2entry	*e;
	int seqno;

	ASSERT(fec_index >= 0);
	ASSERT(fec_index < m_nbFecPkt);
	ASSERT(fec_pkt != NULL);
	ASSERT(m_initialized);
	ASSERT(m_sessionFlags & FLAG_CODER);

	fec_buf = (uintptr_t*)GetBufferPtrOnly(fec_pkt);
	memset(fec_buf, 0, m_pktSize);	// reset buffer (security)

#ifdef LDPC
	if (m_sessionType == TypeLDPC) {
		// LDPC mode so we're encoding with gen matrix
		for (int col = 0; col < m_nbDataPkt; col++) {
			if (mod2dense_get(m_genMatrix, fec_index, col)) {
				to_add_buf = (uintptr_t *)
						GetBuffer(pkt_canvas[col]);
				if (to_add_buf == NULL) {
					fprintf(stderr, "LDPCFecSession::BuildFecPacket: FATAL ERROR, packet %d is not allocated!\n", col);
					return LDPC_ERROR;
				}
				AddToPacket(fec_buf, to_add_buf);
			}
		}
	} else
#endif
	{
		ASSERT(m_sessionType == TypeSTAIRS ||
			m_sessionType == TypeTRIANGLE ||
			m_sessionType == TypeLDGM);
		e = mod2sparse_first_in_row(m_pchkMatrix, fec_index);
		ASSERT(!mod2sparse_at_end(e));
		while (!mod2sparse_at_end(e)) {
			// fec_index in {0.. n-k-1} range, so this test is ok
			if (e->col != fec_index) {
				// don't add fec_pkt to itself
				seqno = GetPktSeqno(e->col);
				to_add_buf = (uintptr_t*)
						GetBuffer(pkt_canvas[seqno]);
				if (to_add_buf == NULL) {
					fprintf(stderr, "LDPCFecSession::BuildFecPacket: FATAL ERROR, packet %d is not allocated!\n", seqno);
					return LDPC_ERROR;
				}
				AddToPacket(fec_buf, to_add_buf);
			}
			e = mod2sparse_next_in_row(e);
		}
	}
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
	if (m_storeData_callback) {
		m_storeData_callback(m_context_4_callback, fec_pkt);
	}
#endif
#ifdef DEBUG
	if (this->m_verbosity >= 1) {
		printf("LDPCFecSession::BuildFecPacket: FEC packet seq=%d created\n",
			fec_index);
	}
#endif
	return LDPC_OK;
}


/******************************************************************************
 * BuildFecPacket: Builds a new FEC packet.
 * => See header file for more informations.
 */
ldpc_error_status
LDPCFecSession::BuildFecPacketsPerCol (void*	pkt_canvas[],
					int	pkt_index,
					int*	(* built_parity_pkts),
					int*	nb_built_parity_pkts)
{

	mod2entry	*e;
	uintptr_t	*data;
	uintptr_t	*fec_pkt;

	ASSERT(m_initialized);
	ASSERT(m_sessionFlags & FLAG_CODER);

	ASSERT(m_sessionType== TypeSTAIRS || m_sessionType == TypeTRIANGLE || m_sessionType== TypeLDGM);

	*nb_built_parity_pkts = 0;	
#ifdef DEBUG
	if (this->m_verbosity >= 1) {
		printf("LDPCFecSession::BuildFecPacketsPerCol: column=%d processed\n", pkt_index);
	}
#endif
	e = mod2sparse_first_in_col(m_pchkMatrix, GetMatrixCol(pkt_index));
	ASSERT(!mod2sparse_at_end(e));

	while (!mod2sparse_at_end(e)) {
		if (e->row != GetMatrixCol(pkt_index)) {
			data = (uintptr_t*)pkt_canvas[pkt_index];
			if (pkt_canvas[GetPktSeqno(e->row)] == NULL) {
				pkt_canvas[GetPktSeqno(e->row)] =
						(char*)calloc(m_pktSize, 1);
			}
			fec_pkt = (uintptr_t*) pkt_canvas[GetPktSeqno(e->row)];
		
			if (data == NULL) {
				fprintf(stderr, "LDPCFecSession::BuildFecPacket: FATAL ERROR, packet %d is not allocated!\n", pkt_index);
				return LDPC_ERROR;
			}
			AddToPacket(fec_pkt, data);
			m_nb_unknown_pkts_encoder[e->row]--;
			if (m_nb_unknown_pkts_encoder[e->row] == 1) {
				(*nb_built_parity_pkts)++;
				if (*nb_built_parity_pkts == 1) {
					*built_parity_pkts = (int*)
						calloc(1,sizeof(int));
				} else {
					*built_parity_pkts = (int*)
						realloc((void*) *built_parity_pkts, (*nb_built_parity_pkts)*sizeof(int));
				}
				*((*built_parity_pkts) + (*nb_built_parity_pkts) - 1) = e->row;						
			}
			
		}		
		e = mod2sparse_next_in_col(e);
	}
	
	/* Call recursively this function with new FEC packets as parameter*/
	int temp = *nb_built_parity_pkts;
	for (int i = 0; i < temp; i++) {
		int	recursive_nb_built_parity_pkts = 0;
		int	*recursive_built_parity_pkts = NULL;

		BuildFecPacketsPerCol(pkt_canvas,
					*built_parity_pkts[i] + m_nbDataPkt,
					&recursive_built_parity_pkts,
					&recursive_nb_built_parity_pkts);
		*built_parity_pkts = (int*) realloc((void*) *built_parity_pkts,((*nb_built_parity_pkts) + recursive_nb_built_parity_pkts)*sizeof(int));
		for (int j = 0; j < recursive_nb_built_parity_pkts; j++) {
			(*built_parity_pkts)[*nb_built_parity_pkts+j] =
						recursive_built_parity_pkts[j];
		}
		*nb_built_parity_pkts = *nb_built_parity_pkts +
					recursive_nb_built_parity_pkts;

		if (recursive_built_parity_pkts != NULL) {
			free(recursive_built_parity_pkts);
			recursive_built_parity_pkts = NULL;
		}
	}
	return LDPC_OK;
}


/******************************************************************************
 * GetMatrixCol:
 * => See header file for more informations.
 */
int
LDPCFecSession::GetMatrixCol(int pktSeqno)
{
	if (pktSeqno < m_nbDataPkt) {
		/* source packet */
#ifdef LDPC
		if (m_sessionType == TypeLDPC) {
			return m_columnsOrder[pktSeqno + m_nbFecPkt];
		} else {
#endif
			return (pktSeqno + m_nbFecPkt);
#ifdef LDPC
		}
#endif
	} else {
		/* parity packet */
#ifdef LDPC
		if (m_sessionType == TypeLDPC) {
			return m_columnsOrder[pktSeqno - m_nbDataPkt];
		} else {
#endif
			return (pktSeqno - m_nbDataPkt);
#ifdef LDPC
		}
#endif
	}
}


/******************************************************************************
 * GetPktSeqno:
 * => See header file for more informations.
 */
int
LDPCFecSession::GetPktSeqno(int matrixCol)
{
	int colInOrder;

#ifdef LDPC
	if (m_sessionType == TypeLDPC) {
		colInOrder = m_columnsIndex[matrixCol];
	} else {
#endif
		colInOrder = matrixCol;
#ifdef LDPC
	}
#endif
	if (colInOrder < m_nbFecPkt) {
		/* parity packet */
		return (colInOrder + m_nbDataPkt);
	} else {
		/* source packet */
		return (colInOrder - m_nbFecPkt);
	}
}


/**
 * DecodeFecStep: Perform a new decoding step with a new (given) packet.
 * This is the legacy front end to the DecodeFecStep() method. The actual
 * work will be done in the other DecodeFecStep() method.
 * => See header file for more informations.
 */ 
ldpc_error_status
LDPCFecSession::DecodeFecStep(	void*	pkt_canvas[],
				void*	new_pkt,
				int	new_pkt_seqno,
				bool	store_packet)
{
	void	*new_pkt_dst;	// temp variable used to store pkt

	ASSERT(new_pkt);
	ASSERT(new_pkt_seqno >= 0);
	ASSERT(new_pkt_seqno < m_nbTotalPkt);
	ASSERT(m_initialized);
	ASSERT(m_sessionFlags & FLAG_DECODER);

	// Fast path. If store packet is not set, then call directly
	// the full DecodeFecStep() method to avoid duplicate processing.
	if (store_packet == false) {
		return(DecodeFecStep(pkt_canvas, new_pkt, new_pkt_seqno)); 
	}
	// Step 0: check if this is a fresh packet, otherwise return
	if ((mod2sparse_last_in_col(m_pchkMatrix, GetMatrixCol(new_pkt_seqno))->row < 0)
	    || (IsDataPkt(new_pkt_seqno) && (pkt_canvas[new_pkt_seqno] != NULL))
	    || (IsParityPkt(new_pkt_seqno) && (m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt] != NULL))) {
		// Packet has already been processed, so skip it
#ifdef DEBUG
		if (this->m_verbosity >= 1) {
			printf("LDPCFecSession::DecodeFecStep: %s packet %d already received or rebuilt, ignored\n",
				(IsDataPkt(new_pkt_seqno)) ? "DATA" : "FEC",
				new_pkt_seqno); }
#endif
		return LDPC_OK;
	}
	// Step 1: Store the packet in a permanent array if the caller wants it.
	// It concerns only DATA packets, since FEC packets are only stored in
	// permanent array if we have a memory gain by doing so, which will
	// be defined later on in the full DecodeFecStep() method.
	if (IsDataPkt(new_pkt_seqno)) {
		ASSERT(store_packet);
		// Call any required callback, or allocate memory, and
		// copy the packet content in it.
		// This is typically something which is done when this
		// function is called recursively, for newly decoded
		// packets.
		if (this->m_decodedPkt_callback != NULL) {
			new_pkt_dst = m_decodedPkt_callback(
						m_context_4_callback,
						m_pktSize,
						new_pkt_seqno);
		} else {
			new_pkt_dst = (void *)malloc(m_pktSize);
		}
		if (new_pkt_dst == NULL) {
			fprintf(stderr, "LDPCFecSession::DecodeFecStep: ERROR, out of memory!\n");
			return LDPC_ERROR;
		}
		// Copy data now
		memcpy(GetBufferPtrOnly(new_pkt_dst), GetBuffer(new_pkt), m_pktSize);
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
		if (m_storeData_callback != NULL) {
			m_storeData_callback(m_context_4_callback,
					new_pkt_dst);
		}
#endif
	} else {
		new_pkt_dst = new_pkt;
	}
	/* continue decoding with the full DecodeFecStep() method */
	return(DecodeFecStep(pkt_canvas, new_pkt_dst, new_pkt_seqno)); 
}


/******************************************************************************
 * DecodeFecStep: Perform a new decoding step with a new (given) packet.
 * => See header file for more informations.
 *
 * This function relies on the following simple algorithm:
 *
 * Given a set of linear equations, if one of them has only one
 * remaining unknown variable, then the value of this variable is
 * that of the constant term.
 * Replace this variable by its value in all remaining linear
 * equations, and reiterate. The value of several variables can
 * therefore be found by this recursive algorithm.
 *
 * In practice, an incoming packet contains the value of the associated
 * variable, so replace its value in all linear equations in which
 * it is implicated. Then apply the above algorithm and see if decoding
 * can progress by one or more steps.
 *
 * For instance, if {s1, s2} are source symbols, and {f1} a FEC symbol:
 *    { s1 + s2 + f1 = 0      (eq. 1)
 *    {      s2 + f1 = 0      (eq. 2)
 * Now if the node receives symbol s2, he replaces its value in the two
 * equations, he then finds f1, he replaces its value in the first equation
 * and finds s1.
 */
ldpc_error_status
LDPCFecSession::DecodeFecStep(	void*	pkt_canvas[],
				void*	new_pkt,
				int	new_pkt_seqno)
{
	mod2entry	*e = NULL;	// entry ("1") in parity check matrix
	mod2entry	*delMe;		// temp: entry to delete in row/column
	void		*currChk;	// temp: pointer to Partial sum
	int		row;		// temp: current row value
	int		*CheckOfDeg1 = NULL; // table of check nodes of degree
					// one after the processing of new_pkt
	int		CheckOfDeg1_nb = 0; // number of entries in table
	int		CheckOfDeg1_listSize = 0; // size of the memory block
					// allocated for the table

	ASSERT(new_pkt);
	ASSERT(new_pkt_seqno >= 0);
	ASSERT(new_pkt_seqno < m_nbTotalPkt);
	ASSERT(m_initialized);
	ASSERT(m_sessionFlags & FLAG_DECODER);

	// Step 0: check if this is a fresh packet, otherwise return
	if ((mod2sparse_last_in_col(m_pchkMatrix, GetMatrixCol(new_pkt_seqno))->row < 0)
	    || (IsDataPkt(new_pkt_seqno) && (pkt_canvas[new_pkt_seqno] != NULL))
	    || (IsParityPkt(new_pkt_seqno) && (m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt] != NULL))) {
		// Packet has already been processed, so skip it
#ifdef DEBUG
		if (this->m_verbosity >= 1) {
			printf("LDPCFecSession::DecodeFecStep: %s packet %d already received or rebuilt, ignored\n",
				(IsDataPkt(new_pkt_seqno)) ? "DATA" : "FEC",
				new_pkt_seqno); }
#endif
		return LDPC_OK;
	}
#ifdef DEBUG
	if (this->m_verbosity >= 1) {
		printf("LDPCFecSession::DecodeFecStep: Processing NEW %s packet: seq=%d\n",
			(IsDataPkt(new_pkt_seqno)) ? "DATA" : "FEC",
			new_pkt_seqno);
	}
#endif
	// First, make sure data is available for this new packet. Must
	// remain valid throughout this function...
	GetBuffer(new_pkt);

	// Step 1: Store the packet in a permanent array. It concerns only DATA
	// packets. FEC packets are only stored in permanent array, if we have
	// a memory gain by doing so (and not creating new partial sums)
	if (IsDataPkt(new_pkt_seqno)) {
		// DATA packet
		// There's no need to allocate anything, nor to call
		// anything. It has already been done by the caller...
		pkt_canvas[new_pkt_seqno] = new_pkt;
#if 0
		}
#endif
	} else {
		// Parity packet
		// Check if parity packet should be stored or if partial
		// sum should be stored
		if (m_triangleWithSmallFECRatio) {
			// In this case, the packet will never be stored into
			// permanent array, but directly added to partial sum
		} else {
			// Check if parity packet should be stored or if
			// partial sum should be stored
			bool	store_parity = false;
			for (e = mod2sparse_first_in_col(m_pchkMatrix,
					    GetMatrixCol(new_pkt_seqno));
			    !mod2sparse_at_end(e);
			    e = mod2sparse_next_in_col(e))
			{
				if (m_nb_unknown_pkts[e->row] > 2) {
					store_parity = true;
					break;
				}
			}
			if (store_parity) {
				// Parity packet will be stored in a permanent array
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
				if (m_allocTmpBuffer_callback != NULL) {
					m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt] =
							m_allocTmpBuffer_callback(
								m_context_4_callback,
								m_pktSize);
				} else
#endif
				{
					m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt] =
							(void *)malloc(m_pktSize);
				}
				// copy the content...
				memcpy(GetBufferPtrOnly(m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt]),
					GetBufferPtrOnly(new_pkt), m_pktSize);
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
				// and store it permanently.
				if (m_storeData_callback) {
					m_storeData_callback(m_context_4_callback,
							m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt]);
				}
#endif
			}
			// else parity packet will only be added to partial sums
		}
	}

	// Step 2: Inject the packet value in each equation it is involved
	// (if partial sum already exists or if partial sum should be created)
	for (e = mod2sparse_first_in_col(m_pchkMatrix, GetMatrixCol(new_pkt_seqno));
	     !mod2sparse_at_end(e); ) {
		// for a given row, ie for a given equation where this packet
		// is implicated, do the following:
		row = e->row;
		m_nb_unknown_pkts[row]--;	// packet is known
		currChk = m_checkValues[row];	// associated check
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
		if (currChk != NULL) {
			// make sure data is available
			if (m_getData_callback != NULL) {
				m_getData_callback(m_context_4_callback, currChk);
			}
		}
#endif
		if (currChk == NULL &&
		    ((m_nb_unknown_pkts[row] == 1) || m_triangleWithSmallFECRatio)
		) {
			// we need to allocate a PS (i.e. check node)
			// and add pkt to it, because the parity packet
			// won't be kept (keep_pkt == false), or it is the
			// last missing packet of this equation, or because
			// or some particular situation where it is non sense
			// no to allocate a PS (m_triangleWithSmallFECRatio).
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
			if (m_allocTmpBuffer_callback != NULL) {
				currChk = m_allocTmpBuffer_callback(
							m_context_4_callback,
							m_pktSize);
			} else
#endif
			{
				currChk = (void*) calloc(m_pktSize32, 4);
			}
			if ((m_checkValues[row] = currChk) == NULL) {
				goto no_mem;
			}
		}
		if (currChk != NULL) {
			// there's a partial sum for this row...
			if (m_nbPkts_in_equ[row] > 1) {
				// we can add the packet content to this PS
				AddToPacket(GetBufferPtrOnly(currChk),
					    GetBufferPtrOnly(new_pkt));
			}
			// else this is useless, since new_pkt is the last
			// pkt of this equation, and its value is necessary
			// equal to the PS. Their sum must be 0 (we don't
			// check it).

			// remove the packet from the equation (this entry
			// is now useless)
			delMe = e;
			e = mod2sparse_next_in_col(e);
			mod2sparse_delete(m_pchkMatrix, delMe);
			m_nbPkts_in_equ[row]--;
			if (IsParityPkt(new_pkt_seqno)) {
				m_nbEqu_for_parity[new_pkt_seqno - m_nbDataPkt]--;
			}

			// Inject all permanently stored packets (DATA and parity)
			// into partial sum
			if (m_triangleWithSmallFECRatio == false)
			{
				// Inject all permanently stored packets
				// (DATA and parity) into this partial sum.
				// Requires to scan the equation (ie row).
				mod2entry	*tmp_e;	// curr pkt in this equ
				int		tmp_seqno;// corresponding seq no
				void		*tmp_pkt; // corresponding pkt pointer

				for (tmp_e = mod2sparse_first_in_row(m_pchkMatrix, row);
				     !mod2sparse_at_end(tmp_e); ) {

					tmp_seqno = GetPktSeqno(tmp_e->col);
					//if (GetPktSeqno(r->col) >= m_nbDataPkt)
					if (IsParityPkt(tmp_seqno)) {
						tmp_pkt = m_parity_pkt_canvas[tmp_seqno - m_nbDataPkt];
					} else {
						// waiting for
						// (m_nb_unknown_pkts[row] == 1)
						// to add source packets is
						// useless... it's even slower
						// in that case!
						tmp_pkt = pkt_canvas[tmp_seqno];
					}
					if (tmp_pkt != NULL) {
						// add the packet content now
						AddToPacket(
							GetBufferPtrOnly(currChk),
							GetBuffer(tmp_pkt));
						// delete the entry
						delMe = tmp_e;
						tmp_e =  mod2sparse_next_in_row(tmp_e);
						mod2sparse_delete(m_pchkMatrix, delMe);
						m_nbPkts_in_equ[row]--;
						if (IsParityPkt(tmp_seqno)) {
							m_nbEqu_for_parity[tmp_seqno - m_nbDataPkt]--;
							// check if we can delete
							// parity packet altogether
							if (m_nbEqu_for_parity[tmp_seqno - m_nbDataPkt] == 0) {
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
								if (m_freePkt_callback != NULL) {
									m_freePkt_callback(
										m_context_4_callback,
										tmp_pkt);
								} else
#endif
								{
									free(tmp_pkt);
								}
								m_parity_pkt_canvas[tmp_seqno - m_nbDataPkt] = NULL;
							}
						}
					} else {
						// this packet not yet known,
						// switch to next one in equ
						tmp_e =  mod2sparse_next_in_row(tmp_e);
					}
				}
			}
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
			// store the partial sum now we are sure it has been
			// completely updated
			if (m_storeData_callback != NULL) {
				m_storeData_callback(m_context_4_callback,
							currChk);
			}
#endif
		} else {
			// here m_checkValues[row] is NULL, ie. the partial
			// sum has not been allocated
			e = mod2sparse_next_in_col(e);
		}
		if (m_nbPkts_in_equ[row] == 1) {
			// register this entry for step 3 since the packet
			// associated to this equation can now be decoded...
			if (CheckOfDeg1 == NULL) {
				// allocate memory for the table first
				CheckOfDeg1_listSize = 4;
				if ((CheckOfDeg1 = (int*)
						calloc(CheckOfDeg1_listSize,
						sizeof(int*))) == NULL) {
					goto no_mem;
				}
			} else if (CheckOfDeg1_nb == CheckOfDeg1_listSize) {
				// not enough size in table, add some more
				CheckOfDeg1_listSize += 4;
				if ((CheckOfDeg1 = (int*)realloc(CheckOfDeg1,
							CheckOfDeg1_listSize * sizeof(int*))) == NULL) {
					goto no_mem;
				}
			}
			CheckOfDeg1[CheckOfDeg1_nb++] = row;
		}
	}

	// Step 3: Check if a new packet has been decoded and take appropriate
	// measures ...
	int	decoded_pkt_seqno;	// sequence number of decoded packet
	//for (int i = 0; i < CheckOfDeg1_nb; i++) 
	for (CheckOfDeg1_nb--; CheckOfDeg1_nb >= 0; CheckOfDeg1_nb--) {
		// get the index (ie row) of the partial sum concerned
		row = CheckOfDeg1[CheckOfDeg1_nb];
		if (m_nbPkts_in_equ[row] == 1) {
			// A new decoded packet is available...
			// NB: because of the recursion below, we need to
			// check that all equations mentioned in the
			// CheckOfDeg1 list are __still__ of degree 1.
			e = mod2sparse_first_in_row(m_pchkMatrix, row);
			ASSERT(!mod2sparse_at_end(e) &&
				mod2sparse_at_end(e->right))
			decoded_pkt_seqno = GetPktSeqno(e->col);
			// remove the entry from the matrix
			currChk = m_checkValues[row];	// remember it
			m_checkValues[row] = NULL;
			m_nbPkts_in_equ[row]--;
			if (IsParityPkt(decoded_pkt_seqno)) {
				m_nbEqu_for_parity[decoded_pkt_seqno - m_nbDataPkt]--;
			}
			mod2sparse_delete(m_pchkMatrix, e);
#ifdef DEBUG
			if (this->m_verbosity >= 1) {
				printf("LDPCFecSession::DecodeFecStep: => REBUILT %s pkt %d\n",
					(IsParityPkt(decoded_pkt_seqno)) ? "FEC" : "DATA",
					decoded_pkt_seqno);
			}
#endif
			if (IsDataPkt(decoded_pkt_seqno)) {
				// Data packet.
				void	*decoded_pkt_dst;// temp variable used to store pkt

				// First copy it into a permanent packet.
				// Call any required callback, or allocate memory, and
				// copy the packet content in it.
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
				if (this->m_decodedPkt_callback != NULL) {
					decoded_pkt_dst =
						m_decodedPkt_callback(
							m_context_4_callback,
							m_pktSize,
							decoded_pkt_seqno);
				} else
#endif
				{
					decoded_pkt_dst =
						(void *)malloc(m_pktSize);
				}
				if (decoded_pkt_dst == NULL) {
					goto no_mem;
				}
				memcpy(GetBufferPtrOnly(decoded_pkt_dst),
					GetBuffer(currChk), m_pktSize);
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
				if (m_storeData_callback != NULL) {
					m_storeData_callback(m_context_4_callback,
							decoded_pkt_dst);
				}
#endif
				// Free partial sum which is no longer used.
				// It's important to free it before calling
				// DecodeFecStep recursively to reduce max
				// memory requirements.
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
				if (m_freePkt_callback != NULL) {
					m_freePkt_callback(m_context_4_callback,
							currChk);
				} else
#endif
				{
					free(currChk);	
				}
				// And finally call this method recursively...
				DecodeFecStep(pkt_canvas, decoded_pkt_dst,
						decoded_pkt_seqno);

			} else {

				// Parity packet.
				// Call this method recursively first...
				DecodeFecStep(pkt_canvas, currChk, decoded_pkt_seqno);
				// Then free the partial sum which is no longer needed.
#ifdef EXTERNAL_MEMORY_MGMT_SUPPORT
				if (m_freePkt_callback != NULL) {
					m_freePkt_callback(m_context_4_callback,
							currChk);
				} else
#endif
				{
					free(currChk);	
				}
			}
		}
	}
	if (CheckOfDeg1 != NULL) {
		free(CheckOfDeg1);
	}
	return LDPC_OK;

no_mem:
	fprintf(stderr, "LDPCFecSession::DecodeFecStep: ERROR, out of memory!\n");
	return LDPC_ERROR;
}


/******************************************************************************
 * IsAlreadyKnown: Returns true if the packet has already been received
 * or decoded (i.e. if it is already known), false otherwise.
 * => See header file for more informations.
 */
bool
LDPCFecSession::PacketAlreadyKnown (void*	pkt_canvas[],
				    int		new_pkt_seqno)
{
	if ((mod2sparse_last_in_col(m_pchkMatrix, GetMatrixCol(new_pkt_seqno))->row < 0)
	    || (IsDataPkt(new_pkt_seqno) && (pkt_canvas[new_pkt_seqno] != NULL))
	    || (IsParityPkt(new_pkt_seqno) && (m_parity_pkt_canvas[new_pkt_seqno - m_nbDataPkt] != NULL))) {
		// No entry in the column associated to this packet.
		// Means packet has already been processed, so skip it.
#ifdef DEBUG
		if (this->m_verbosity >= 1) {
			printf("LDPCFecSession::PacketAlreadyKnown: %s packet %d already received or rebuilt\n",
				(new_pkt_seqno < m_nbDataPkt) ? "DATA" : "FEC",
				new_pkt_seqno);
		}
#endif
		return true;
	} else {
#ifdef DEBUG
		if (this->m_verbosity >= 1) {
			printf("LDPCFecSession::PacketAlreadyKnown: %s packet %d not received or rebuilt\n",
				(new_pkt_seqno < m_nbDataPkt) ? "DATA" : "FEC",
				new_pkt_seqno);
		}
#endif
		return false;
	}
}


/******************************************************************************
 * IsDecodingComplete: Checks if all DATA packets have been received/rebuilt.
 * => See header file for more informations.
 */
bool
LDPCFecSession::IsDecodingComplete(void*	pkt_canvas[])
{
	if (!m_initialized) {
		fprintf(stderr, "LDPCFecSession::IsDecodingComplete: ERROR: LDPC Session is NOT initialized!\n");
		return false;
	}

	for (int i = m_firstNonDecoded; i < m_nbDataPkt; i++) {
		if (pkt_canvas[i] == NULL) {
			/* not yet decoded! */
			m_firstNonDecoded = i;	/* remember for next time */
			return false;
		}
	}
	return true;
}

