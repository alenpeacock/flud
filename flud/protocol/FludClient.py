"""
FludClient.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

flud client ops.
"""

import os
import stat
import logging

from .ClientPrimitives import *
from .ClientDHTPrimitives import *

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

    async def get_id(self, host, port):
        return await send_get_id(self.node, host, port)

    def sendGetID(self, host, port):
        return self.node.async_runtime.deferred_from_coro(self.get_id(host, port))

    async def async_sendGetID(self, host, port):
        return await self.get_id(host, port)

    # XXX: we should cache nKu so that we don't do the GETID for all of these
    # ops every single time
    async def store(self, filename, metadata, host, port, nKu=None):
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
            logger.debug("returning saved store op for %s in store"
                    % filename)
            return await self.currentStorOps[key]

        if not nKu:
            logger.warn("not doing AggregateStore on small file because"
                    " of missing nKu")
            print("not doing AggregateStore on small file because" \
                    " of missing nKu")
            nKu = await self.get_id(host, port)

        fsize = os.stat(filename)[stat.ST_SIZE];
        if fsize < MINSTORSIZE:
            logger.debug("doing AggStore")
            if metadata:
                logger.debug("with metadata")
            operation = aggregate_store(
                    nKu, self.node, host, port, filename, metadata)
        else:
            logger.debug("SENDSTORE")
            operation = send_store_request(
                    nKu, self.node, host, port, filename, metadata)
        self.currentStorOps[key] = operation
        try:
            return await operation
        finally:
            self.currentStorOps.pop(key, None)

    def sendStore(self, filename, metadata, host, port, nKu=None):
        return self.node.async_runtime.deferred_from_coro(
            self.store(filename, metadata, host, port, nKu)
        )

    async def async_sendStore(self, filename, metadata, host, port, nKu=None):
        return await self.store(filename, metadata, host, port, nKu)
    
    # XXX: need a version that takes a metakey, too
    async def retrieve(self, filekey, host, port, nKu=None, metakey=True):
        if not nKu:
            nKu = await self.get_id(host, port)
        return await send_retrieve(
                nKu, self.node, host, port, filekey, metakey)

    def sendRetrieve(self, filekey, host, port, nKu=None, metakey=True):
        return self.node.async_runtime.deferred_from_coro(
            self.retrieve(filekey, host, port, nKu, metakey)
        )

    async def async_sendRetrieve(self, filekey, host, port, nKu=None,
            metakey=True):
        return await self.retrieve(filekey, host, port, nKu, metakey)
    
    async def verify(self, filekey, offset, length, host, port, nKu=None,
            meta=None):
        if not nKu:
            nKu = await self.get_id(host, port)
        return await send_verify(
                nKu, self.node, host, port, filekey, offset, length, meta)

    def sendVerify(self, filekey, offset, length, host, port, nKu=None, 
            meta=None):
        return self.node.async_runtime.deferred_from_coro(
            self.verify(filekey, offset, length, host, port, nKu, meta)
        )

    async def async_sendVerify(self, filekey, offset, length, host, port,
            nKu=None, meta=None):
        return await self.verify(filekey, offset, length, host, port, nKu, meta)
    
    async def delete(self, filekey, metakey, host, port, nKu=None):
        if not nKu:
            nKu = await self.get_id(host, port)
        return await send_delete(
                nKu, self.node, host, port, filekey, metakey)

    def sendDelete(self, filekey, metakey, host, port, nKu=None):
        return self.node.async_runtime.deferred_from_coro(
            self.delete(filekey, metakey, host, port, nKu)
        )

    async def async_sendDelete(self, filekey, metakey, host, port, nKu=None):
        return await self.delete(filekey, metakey, host, port, nKu)
    
    """
    DHT single primitives (single call to single peer).  These should probably
    only be called for testing or bootstrapping (sendkFindNode can be used to
    'connect' to the flud network via a gateway, for instance).  Use the
    recursive primitives for doing DHT ops.
    """
    async def send_k_find_node(self, host, port, key):
        return await send_kfindnode(self.node, host, port, key)

    def sendkFindNode(self, host, port, key):
        return self.node.async_runtime.deferred_from_coro(
            self.send_k_find_node(host, port, key)
        )

    async def async_sendkFindNode(self, host, port, key):
        return await self.send_k_find_node(host, port, key)

    async def send_k_store(self, host, port, key, val):
        return await send_kstore(self.node, host, port, key, val)

    def sendkStore(self, host, port, key, val):
        return self.node.async_runtime.deferred_from_coro(
            self.send_k_store(host, port, key, val)
        )

    async def async_sendkStore(self, host, port, key, val):
        return await self.send_k_store(host, port, key, val)

    async def send_k_find_value(self, host, port, key):
        return await send_kfindvalue(self.node, host, port, key)

    def sendkFindValue(self, host, port, key):
        return self.node.async_runtime.deferred_from_coro(
            self.send_k_find_value(host, port, key)
        )

    async def async_sendkFindValue(self, host, port, key):
        return await self.send_k_find_value(host, port, key)
    
    """
    DHT recursive primitives (recursive calls to muliple peers)
    """
    async def k_find_node(self, key):
        return await async_kFindNode(self.node, key)

    def kFindNode(self, key):
        return self.node.async_runtime.deferred_from_coro(self.k_find_node(key))

    async def async_kFindNode(self, key):
        return await self.k_find_node(key)
    
    async def k_store(self, key, val):
        return await async_kStore(self.node, key, val)

    def kStore(self, key, val):
        return self.node.async_runtime.deferred_from_coro(self.k_store(key, val))

    async def async_kStore(self, key, val):
        return await self.k_store(key, val)
    
    async def k_find_value(self, key):
        return await async_kFindValue(self.node, key)

    def kFindValue(self, key):
        return self.node.async_runtime.deferred_from_coro(self.k_find_value(key))

    async def async_kFindValue(self, key):
        return await self.k_find_value(key)
    
