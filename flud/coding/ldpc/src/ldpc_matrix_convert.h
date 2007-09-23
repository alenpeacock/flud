/* MOD2CONVERT.H - Routines converting between sparse and dense mod2 matrices.*/
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


#ifndef LDPC_MATRIX_CONVERT__
#define LDPC_MATRIX_CONVERT__

#include "ldpc_matrix_dense.h"
#include "ldpc_matrix_sparse.h"
#include "tools.h"


void mod2sparse_to_dense (mod2sparse *, mod2dense *);
void mod2dense_to_sparse (mod2dense *, mod2sparse *);

#endif

