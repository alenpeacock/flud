/*
 * The contents of this directory and its sub-directories are 
 * Copyright (c) 1995-2003 by Radford M. Neal
 * 
 * Permission is granted for anyone to copy, use, modify, or distribute these
 * programs and accompanying documents for any purpose, provided this copyright
 * notice is retained and prominently displayed, along with a note saying 
 * that the original programs are available from Radford Neal's web page, and 
 * note is made of any changes made to these programs.  These programs and 
 * documents are distributed without any warranty, express or implied.  As the
 * programs were written for research purposes only, they have not been tested 
 * to the degree that would be advisable in any important application.  All use
 * of these programs is entirely at the user's own risk.
 */


#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "ldpc_create_gen.h"
#include "ldpc_matrix_dense.h"
#include "ldpc_matrix_sparse.h"
#include "ldpc_matrix_convert.h"


mod2dense* CreateGenMatrix( mod2sparse* pchkMatrix, int *columnsOrder )
{ 
	mod2dense* pchkMatrixDense;
	mod2dense *A, *A2, *AI, *B;
	int i, redundant;
	int *rows_inv;
	int M = pchkMatrix->n_rows;
	int N = pchkMatrix->n_cols;
	int* rows;
	mod2dense* genMatrix;

	if (N<=M)
	{
		printf("ERROR: Can't encode if number of bits (%d) isn't greater than number of checks (%d)\n",N,M);
		exit(1);
	}

	/* Allocate space for row and column permutations. */
	//columnsOrder = (int*)chk_alloc ( N, sizeof(int) );
	rows = (int*)chk_alloc ( M, sizeof(int) );

	AI = mod2dense_allocate( M, M );
	B  = mod2dense_allocate( M, N-M );
	genMatrix  = mod2dense_allocate( M, N-M );

	pchkMatrixDense = mod2dense_allocate( M, N );
	mod2sparse_to_dense( pchkMatrix, pchkMatrixDense );

	/* invert using whatever selection of rows/columns is needed to get a non-singular sub-matrix. */
	A  = mod2dense_allocate( M, N );
	A2 = mod2dense_allocate( M, N );

	redundant = mod2dense_invert_selected( pchkMatrixDense, A2, rows, columnsOrder );
	/* pchkMatrixDense was destroyed by invert_selected */
	mod2sparse_to_dense( pchkMatrix, pchkMatrixDense );

	if ( redundant > 0 )
	{
		printf( "Note: Parity check matrix has %d redundant checks\n", redundant );
	}

	rows_inv = (int*)chk_alloc (M, sizeof *rows_inv);

	for (i = 0; i<M; i++)
	{
		rows_inv[rows[i]] = i;
	}

	mod2dense_copyrows( A2, A, rows );
	mod2dense_copycols( A, A2, columnsOrder );
	mod2dense_copycols( A2, AI, rows_inv );

	mod2dense_copycols( pchkMatrixDense, B, columnsOrder+M );

	/* Form final generator matrix. */
	mod2dense_multiply( AI, B, genMatrix );

	//printf("\n");
	//for(int x=0; x<M; x++)
	//{
	//	printf("%d ", rows[x]);
	//}
	//printf("\n");

	/* Compute and print number of 1s. */
	//c = 0;
	//for (i = 0; i<M; i++)
	//{
	//	for (j = 0; j<N-M; j++)
	//	{
	//		c += mod2dense_get(genMatrix,i,j);
	//	}
	//}
	//fprintf(stderr, "Number of 1s per check in Inv(A) X B is %.1f\n", (double)c/M);

	mod2dense_free( pchkMatrixDense );
	mod2dense_free( A );
	mod2dense_free( A2 );
	mod2dense_free( AI );
	mod2dense_free( B );
	free(rows);
	free(rows_inv);

	return genMatrix;
}

