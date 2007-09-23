/* Copyright (C) 1995,1996,1997,1998,2001,2002 Free Software Foundation, Inc.
   This file is part of the GNU C Library.
   Contributed by Ulrich Drepper <drepper@gnu.ai.mit.edu>, August 1995.

   The GNU C Library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 2.1 of the License, or (at your option) any later version.

   The GNU C Library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with the GNU C Library; if not, write to the Free
   Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
   02111-1307 USA.  */

#include "ldpc_rand.h"

#ifndef WIN32
#include <inttypes.h>
#endif

#define NULL (void *)0

/* Global state for non-reentrant functions.  */
struct ldpc_drand48_data __ldpc_drand48_data;

int
__srand48_r (long int seedval, struct ldpc_drand48_data * buffer)
{
  /* The standards say we only have 32 bits.  */
  if (sizeof (long int) > 4)
    seedval &= 0xffffffffl;

  buffer->__x[2] = seedval >> 16;
  buffer->__x[1] = seedval & 0xffffl;
  buffer->__x[0] = 0x330e;

#ifndef WIN32
  buffer->__a = 0x5deece66dull;
#else
  buffer->__a = (unsigned __int64) 0x5deece66d;
#endif
  buffer->__c = 0xb;
  buffer->__init = 1;

  return 0;
}


void
ldpc_srand48 (long seedval)
{
  (void) __srand48_r (seedval, &__ldpc_drand48_data);
}

int
__drand48_iterate (unsigned short int xsubi[3], struct ldpc_drand48_data *buffer)
{
#ifndef WIN32
  uint64_t X;
  uint64_t result;
#else
  unsigned __int64 X;
  unsigned __int64 result;
#endif

  /* Initialize buffer, if not yet done.  */
  if (!buffer->__init)
    {	
    
    	  buffer->__x[2] = 0;
          buffer->__x[1] = 0;  
 	  buffer->__x[0] = 0;
    
#ifndef WIN32
	  buffer->__a = 0x5deece66dull;
#else
	  buffer->__a = (unsigned __int64) 0x5deece66d;
#endif
	  buffer->__c = 0xb;  
      buffer->__init = 1;
    }

  /* Do the real work.  We choose a data type which contains at least
     48 bits.  Because we compute the modulus it does not care how
     many bits really are computed.  */

#ifndef WIN32
  X = (uint64_t) xsubi[2] << 32 | (uint32_t) xsubi[1] << 16 | xsubi[0];
#else
  X = (unsigned __int64) xsubi[2] << 32 | (unsigned __int32) xsubi[1] << 16 | xsubi[0];
#endif

  result = X * buffer->__a + buffer->__c;

  xsubi[0] = result & 0xffff;
  xsubi[1] = (result >> 16) & 0xffff;
  xsubi[2] = (result >> 32) & 0xffff;

  return 0;
}


int
__nrand48_r (unsigned short int xsubi[3], struct ldpc_drand48_data *buffer, long int *result)
{
  /* Compute next state.  */
  if (__drand48_iterate (xsubi, buffer) < 0)
    return -1;

  /* Store the result.  */
  if (sizeof (unsigned short int) == 2)
    *result = xsubi[2] << 15 | xsubi[1] >> 1;
  else
    *result = xsubi[2] >> 1;

  return 0;
}


int
lrand48_r (struct ldpc_drand48_data *buffer, long int *result)
{
  /* Be generous for the arguments, detect some errors.  */
  if (buffer == NULL)
   return -1;

  return __nrand48_r (buffer->__x, buffer, result);
}

long int
ldpc_lrand48 ()
{
  long int result;

  (void) __nrand48_r (__ldpc_drand48_data.__x, &__ldpc_drand48_data, &result);

  return result;
}
