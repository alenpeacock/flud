"""
ConnectionQueue, (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

This module manages the connection queue.  In order to reduce the 
probability of the reactor getting tied up servicing requests/responses
during periods of extreme busy-ness (and thus 'starving' some ops, 
causing TimeoutErrors), we throttle the number of outstanding requests
that we send to MAXOPS.  The rest, we put in the 'waiting' queue, and
these are popped off when a spot becomes available.  
"""

import logging

MAXOPS = 80      # maximum number of concurrent connections to maintain 
pending = 0      # number of current connections
waiting = []     # queue of waiting connections to make.  This queue contains
                 # tuples.  The first element of the tuple must have a 
				 # startRequest() func that takes the rest of the tuple as
				 # arguments.

logger = logging.getLogger("flud.client.connq")

def checkWaiting(resp, finishedOne=True):
	"""
	This function pops items off the waiting queue and invokes their
	startRequest() method.  It should eventually be called by any process that
	also calls queueWaiting() (usually as part of callback/errback chain).  The
	'resp' object passed in will be returned (so that this function can sit
	transparently in the errback/callback chain).
	"""
	numwaiting = len(waiting)
	logger.debug("in checkWaiting, len(waiting) = %d" % numwaiting)
	#print "resp = %s..." % fencode(long(resp,16))[:8]
	#print "resp = %s..." % str(resp)
	global pending
	if finishedOne:
		pending = pending - 1
		logger.debug("decremented pending to %s" % pending)
	if numwaiting > 0 and pending < MAXOPS:
		saved = waiting.pop(0)
		Req = saved[0]
		args = saved[1:]
		logger.debug("w: %d, p: %d, restoring Request %s(%s)" % (numwaiting, 
				pending, Req.__class__.__name__, str(args)))
		Req.startRequest(*args)
		pending += 1
	return resp

def enqueue(requestTuple):
	"""
	Adds a requestTuple to those waiting.  The first element of the tuple must
	have a startRequest() func that takes the rest of the tuple as arguments.
	This startRequest() function will be called with those arguments when it
	comes off the queue (via checkWaiting).
	"""
	waiting.append(requestTuple)
	logger.debug("trying to do %s now..." % requestTuple[0].__class__.__name__)
	checkWaiting(None, finishedOne=False)
