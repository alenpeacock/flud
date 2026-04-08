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
        self.current_store_tasks = {}
    
    """
    Data storage primitives
    """
    async def get_id(self, host, port):
        return await send_get_id(self.node, host, port)

    # XXX: we should cache nKu so that we don't do the GETID for all of these
    # ops every single time
    async def store(self, filename, metadata, host, port, nKu=None):
        # XXX: need to keep a map of 'filename' to in-flight tasks, in case we are
        # asked to store the same chunk more than once concurrently (happens
        # for 0-byte files or from identical copies of the same file, for
        # example).  both SENDSTORE and AggregateStore will choke on this.
        # if we find a store request in said map, just return that task instead
        # of redoing the op. [note, could mess up node choice... should also do
        # this on whole-file level in FileOps]

        # XXX: need to remove from current_store_tasks on success or failure
        key = "%s:%d:%s" % (host, port, filename)

        if key in self.current_store_tasks:
            logger.debug("returning saved store op for %s in store"
                    % filename)
            return await self.current_store_tasks[key]

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
        self.current_store_tasks[key] = operation
        try:
            return await operation
        finally:
            self.current_store_tasks.pop(key, None)

    # XXX: need a version that takes a metakey, too
    async def retrieve(self, filekey, host, port, nKu=None, metakey=True):
        if not nKu:
            nKu = await self.get_id(host, port)
        return await send_retrieve(
                nKu, self.node, host, port, filekey, metakey)
    
    async def verify(self, filekey, offset, length, host, port, nKu=None,
            meta=None):
        if not nKu:
            nKu = await self.get_id(host, port)
        return await send_verify(
                nKu, self.node, host, port, filekey, offset, length, meta)

    async def delete(self, filekey, metakey, host, port, nKu=None):
        if not nKu:
            nKu = await self.get_id(host, port)
        return await send_delete(
                nKu, self.node, host, port, filekey, metakey)
    
    """
    DHT single primitives (single call to single peer).  These should probably
    only be called for testing or bootstrapping (`send_k_find_node` can be used to
    'connect' to the flud network via a gateway, for instance).  Use the
    recursive primitives for doing DHT ops.
    """
    async def send_k_find_node(self, host, port, key):
        return await send_k_find_node(self.node, host, port, key)

    async def send_k_store(self, host, port, key, val):
        return await send_k_store(self.node, host, port, key, val)

    async def send_k_find_value(self, host, port, key):
        return await send_k_find_value(self.node, host, port, key)
    
    """
    DHT recursive primitives (recursive calls to muliple peers)
    """
    async def k_find_node(self, key):
        return await k_find_node(self.node, key)
    
    async def k_store(self, key, val):
        return await k_store(self.node, key, val)
    
    async def k_find_value(self, key):
        return await k_find_value(self.node, key)
    
