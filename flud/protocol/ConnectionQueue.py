"""
ConnectionQueue, (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

This module manages the connection queue.  In order to reduce the 
probability of the reactor getting tied up servicing requests/responses
during periods of extreme busy-ness (and thus 'starving' some ops, 
causing TimeoutErrors), we throttle the number of outstanding requests
that we send to MAXOPS.  The rest, we put in the 'waiting' queue, and
these are popped off when a spot becomes available.  
"""

import logging
import threading
from twisted.python import failure as twfailure

MAXOPS = 80      # maximum number of concurrent connections to maintain 
pending = 0      # number of current connections
waiting = []     # queue of waiting connections to make.  This queue contains
                 # tuples.  The first element of the tuple must have a 
                 # startRequest() func that takes the rest of the tuple as
                 # arguments.

logger = logging.getLogger("flud.client.connq")
_state_lock = threading.Lock()

def checkWaiting(resp, finishedOne=True):
    """
    This function pops items off the waiting queue and invokes their
    startRequest() method.  It should eventually be called by any process that
    also calls queueWaiting() (usually as part of callback/errback chain).  The
    'resp' object passed in will be returned (so that this function can sit
    transparently in the errback/callback chain).
    """
    #print "resp = %s..." % fencode(long(resp,16))[:8]
    #print "resp = %s..." % str(resp)
    global pending
    with _state_lock:
        if finishedOne:
            if pending > 0:
                pending -= 1
                logger.debug("decremented pending to %s" % pending)
            else:
                logger.debug("pending already 0 at completion boundary")
        numwaiting = len(waiting)
        logger.debug("in checkWaiting, len(waiting) = %d" % numwaiting)
        if numwaiting == 0 or pending >= MAXOPS:
            return resp
        saved = waiting.pop(0)
        pending += 1
        current_pending = pending
        remaining_waiting = len(waiting)

    Req = saved[0]
    args = saved[1:]
    logger.debug("w: %d, p: %d, restoring Request %s(%s)"
            % (remaining_waiting, current_pending, Req.__class__.__name__,
                str(args)))
    try:
        Req.startRequest(*args)
    except Exception as exc:
        with _state_lock:
            if pending > 0:
                pending -= 1
        logger.warn("startRequest failed for %s: %s",
                Req.__class__.__name__, str(exc))
        if hasattr(Req, "deferred"):
            try:
                if not Req.deferred.called:
                    Req.deferred.errback(twfailure.Failure(exc))
            except Exception:
                pass
    return resp

def enqueue(requestTuple):
    """
    Adds a requestTuple to those waiting.  The first element of the tuple must
    have a startRequest() func that takes the rest of the tuple as arguments.
    This startRequest() function will be called with those arguments when it
    comes off the queue (via checkWaiting).
    """
    with _state_lock:
        waiting.append(requestTuple)
    logger.debug("trying to do %s now..." % requestTuple[0].__class__.__name__)
    checkWaiting(None, finishedOne=False)
