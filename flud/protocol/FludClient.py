"""
FludClient.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

flud client ops. 
"""

from twisted.web import client
from twisted.internet import error
import os, stat, http.client, sys, logging

from .ClientPrimitives import *
from .ClientDHTPrimitives import *
from .ClientPrimitives import _use_async_http
from . import FludCommUtil
from flud.async_runtime import maybe_await

logger = logging.getLogger('flud.client')

class FludClient(object):
    """
    This class contains methods which create request objects
    """
    def __init__(self, node):
        self.node = node
        self.currentStorOps = {}
    
    """
    Data storage primitives
    """
    def redoTO(self, f, node, host, port):
        print("in redoTO: %s" % f)
        #print "in redoTO: %s" % dir(f.getTraceback())
        if f.getTraceback().find("error.TimeoutError"): 
            print("retrying........")
            return self.sendGetID(host, port)
        else:
            return f

    def sendGetID(self, host, port):
        sender = SENDGETID_ASYNC if _use_async_http() else SENDGETID
        d = sender(self.node, host, port).deferred
        #d.addErrback(self.redoTO, self.node, host, port)
        return d

    async def async_sendGetID(self, host, port):
        return await maybe_await(self.sendGetID(host, port))

    # XXX: we should cache nKu so that we don't do the GETID for all of these
    # ops every single time
    def sendStore(self, filename, metadata, host, port, nKu=None):
        # XXX: need to keep a map of 'filename' to deferreds, in case we are
        # asked to store the same chunk more than once concurrently (happens
        # for 0-byte files or from identical copies of the same file, for
        # example).  both SENDSTORE and AggregateStore will choke on this.
        # if we find a store req in said map, just return that deferred instead
        # of redoing the op. [note, could mess up node choice... should also do
        # this on whole-file level in FileOps]

        # XXX: need to remove from currentStorOps on success or failure
        key = "%s:%d:%s" % (host, port, filename)

        if key in self.currentStorOps:
            logger.debug("returning saved deferred for %s in sendStore" 
                    % filename)
            return self.currentStorOps[key]

        def sendStoreWithnKu(nKu, host, port, filename, metadata):
            sender = SENDSTORE_ASYNC if _use_async_http() else SENDSTORE
            return sender(nKu, self.node, host, port, filename,
                    metadata).deferred

        def removeKey(r, key):
            self.currentStorOps.pop(key)
            return r

        if not nKu:
            # XXX: doesn't do AggregateStore if file is small.  Can fix by
            #      moving this AggStore v. SENDSTORE choice into SENDSTORE 
            #      proper
            logger.warn("not doing AggregateStore on small file because"
                    " of missing nKu")
            print("not doing AggregateStore on small file because" \
                    " of missing nKu")
            d = self.sendGetID(host, port)
            d.addCallback(sendStoreWithnKu, host, port, filename, metadata)
            self.currentStorOps[key] = d
            return d

        fsize = os.stat(filename)[stat.ST_SIZE];
        if fsize < MINSTORSIZE:
            logger.debug("doing AggStore")
            if metadata:
                logger.debug("with metadata")
            d = AggregateStore(nKu, self.node, host, port, filename, 
                    metadata).deferred
        else:
            logger.debug("SENDSTORE")
            sender = SENDSTORE_ASYNC if _use_async_http() else SENDSTORE
            d = sender(nKu, self.node, host, port, filename,
                    metadata).deferred
        self.currentStorOps[key] = d
        d.addBoth(removeKey, key)
        return d

    async def async_sendStore(self, filename, metadata, host, port, nKu=None):
        return await maybe_await(
            self.sendStore(filename, metadata, host, port, nKu)
        )
    
    # XXX: need a version that takes a metakey, too
    def sendRetrieve(self, filekey, host, port, nKu=None, metakey=True):
        def sendRetrieveWithNKu(nKu, host, port, filekey, metakey=True):
            sender = SENDRETRIEVE_ASYNC if _use_async_http() else SENDRETRIEVE
            return sender(nKu, self.node, host, port, filekey,
                    metakey).deferred

        if not nKu:
            d = self.sendGetID(host, port)
            d.addCallback(sendRetrieveWithNKu, host, port, filekey, metakey)
            return d
        else:
            sender = SENDRETRIEVE_ASYNC if _use_async_http() else SENDRETRIEVE
            return sender(nKu, self.node, host, port, filekey,
                    metakey).deferred

    async def async_sendRetrieve(self, filekey, host, port, nKu=None,
            metakey=True):
        return await maybe_await(
            self.sendRetrieve(filekey, host, port, nKu, metakey)
        )
    
    def sendVerify(self, filekey, offset, length, host, port, nKu=None, 
            meta=None):
        def sendVerifyWithNKu(nKu, host, port, filekey, offset, length, 
                meta=True):
            sender = SENDVERIFY_ASYNC if _use_async_http() else SENDVERIFY
            return sender(nKu, self.node, host, port, filekey, offset,
                    length, meta).deferred

        if not nKu:
            d = self.sendGetID(host, port)
            d.addCallback(sendVerifyWithNKu, host, port, filekey, offset, 
                    length, meta)
            return d
        else:
            sender = SENDVERIFY_ASYNC if _use_async_http() else SENDVERIFY
            s = sender(nKu, self.node, host, port, filekey, offset, length,
                    meta)
            return s.deferred

    async def async_sendVerify(self, filekey, offset, length, host, port,
            nKu=None, meta=None):
        return await maybe_await(
            self.sendVerify(filekey, offset, length, host, port, nKu, meta)
        )
    
    def sendDelete(self, filekey, metakey, host, port, nKu=None):
        def sendDeleteWithNKu(nKu, host, port, filekey, metakey):
            sender = SENDDELETE_ASYNC if _use_async_http() else SENDDELETE
            return sender(nKu, self.node, host, port, filekey,
                    metakey).deferred

        if not nKu:
            d = self.sendGetID(host, port)
            d.addCallback(sendDeleteWithNKu, host, port, filekey, metakey)
            return d
        else:
            sender = SENDDELETE_ASYNC if _use_async_http() else SENDDELETE
            return sender(nKu, self.node, host, port, filekey,
                    metakey).deferred

    async def async_sendDelete(self, filekey, metakey, host, port, nKu=None):
        return await maybe_await(
            self.sendDelete(filekey, metakey, host, port, nKu)
        )
    
    """
    DHT single primitives (single call to single peer).  These should probably
    only be called for testing or bootstrapping (sendkFindNode can be used to
    'connect' to the flud network via a gateway, for instance).  Use the
    recursive primitives for doing DHT ops.
    """
    def sendkFindNode(self, host, port, key):
        sender = SENDkFINDNODE_ASYNC if _use_async_http() else SENDkFINDNODE
        return sender(self.node, host, port, key).deferred

    async def async_sendkFindNode(self, host, port, key):
        return await maybe_await(self.sendkFindNode(host, port, key))

    def sendkStore(self, host, port, key, val):
        sender = SENDkSTORE_ASYNC if _use_async_http() else SENDkSTORE
        return sender(self.node, host, port, key, val).deferred

    async def async_sendkStore(self, host, port, key, val):
        return await maybe_await(self.sendkStore(host, port, key, val))

    def sendkFindValue(self, host, port, key):
        sender = SENDkFINDVALUE_ASYNC if _use_async_http() else SENDkFINDVALUE
        return sender(self.node, host, port, key).deferred

    async def async_sendkFindValue(self, host, port, key):
        return await maybe_await(self.sendkFindValue(host, port, key))
    
    """
    DHT recursive primitives (recursive calls to muliple peers)
    """
    def kFindNode(self, key):
        return kFindNode(self.node, key).deferred

    async def async_kFindNode(self, key):
        return await maybe_await(self.kFindNode(key))
    
    def kStore(self, key, val):
        return kStore(self.node, key, val).deferred

    async def async_kStore(self, key, val):
        return await maybe_await(self.kStore(key, val))
    
    def kFindValue(self, key):
        return kFindValue(self.node, key).deferred

    async def async_kFindValue(self, key):
        return await maybe_await(self.kFindValue(key))
    
