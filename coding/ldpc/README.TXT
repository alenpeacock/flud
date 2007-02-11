	$Id: README.TXT,v 1.1 2006/07/16 06:05:02 alen Exp $

	--------------------------------------------
	LDPC/LDGM Large Block FEC Codec, README File
	--------------------------------------------


This software is written in C++, and has been compiled and tested on 
different operating systems :
- Linux (kernel 2.4.x/2.6.x with g++ 3.x)
- Solaris 2.8
- FreeBSD
- Windows 2000/XP (with Microsoft Visual C++ 7, solution files included)

This LDPC codec is the only Open-Source, patent free, large block
FEC codec for the Packet Erasure Channel (e.g. Internet) available
as of today, to the best of our knowledge.

Traditional small block Forward Error Correction (FEC) codes, like the 
Reed-Solomon erasure (RSE) code, are known to raise efficiency problems
in particular when they are applied to the Asynchronous Layered Coding
(ALC) reliable multicast protocol. We have therefore designed a large
block FEC codec, derived from the well known Low-Density Parity Check
(LDPC) codes, and capable of operating on source blocks that are several
tens or hundreds of megabytes long. This work is based on the theoretical
work done by Gallager in the early 1960's.

A very detailed description and performance evaluation of the codec 
is available:``Design, Evaluation and Comparison of Four Large Block 
FEC Codecs, LDPC, LDGM, LDGM Staircase and LDGM Triangle, plus a 
Reed-Solomon Small Block FEC Codec'',
V. Roca, C. Neumann, - INRIA Research Report RR-5225, June 2004.

   http://www.inrialpes.fr/planete/people/roca/doc/rr04_fec_comparision.ps.gz
   http://www.inrialpes.fr/planete/people/roca/doc/rr04_fec_comparision.pdf

Some early results and a description of the background, our codec 
is also available: ``Design and Evaluation of a 
Low Density Generator Matrix (LDGM) large block FEC codec''
V. Roca, Z. Khallouf, J. Laboure - Fifth International Workshop on
Networked Group Communication (NGC'03), Munich, Germany, September 2003.

   http://www.inrialpes.fr/planete/people/roca/doc/ngc03_ldpc.ps.gz
   http://www.inrialpes.fr/planete/people/roca/doc/ngc03_ldpc.pdf

This codec is both integrated in our MCLv3 library (more infos at
http://www.inrialpes.fr/planete/people/roca/mcl/) and distributed 
independantly (in the LDPC source distribution). Therefore, it can
easily be used by other external applications or libraries. Several
such sample applications are provided in the LDPC distribution to
facilitate its integration into legacy applications, and information
provided in both the man pages and FAQ.TXT file. 

Note that this codec is still work in progress and we expect to further
improve the already promising results.

This codec is: 

Copyright (c) 2002-2005 INRIA - All rights reserved
Copyright (c) 1995-2003 by Radford M. Neal

It includes large portions of code written by Radford Neal
available at http://www.cs.toronto.edu/~radford/ldpc.software.html

