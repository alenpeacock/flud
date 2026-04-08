"""
FludCommUtil.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

Communications routines used by both client and server code.
"""
import logging, socket
import inspect

from flud.FludExceptions import FludException
from flud.FludCrypto import FludRSA
from flud.defer import failure


"""
Some constants used by the Flud Protocol classes
"""
PROTOCOL_VERSION = '0.2'
# XXX: when things timeout, bad news.  Unintuitive exceptions spewed.  Make this
#      small and fix all issues.
primitive_to = 3800 # default timeout for primitives
kprimitive_to = primitive_to/2  # default timeout for kademlia primitives
#kprimitive_to = 10 # default timeout for kademlia primitives
transfer_to = 3600 # 10-hr limit on file transfers
MAXTIMEOUTS = 5  # number of times to retry after connection timeout failure
CONNECT_TO = 60
CONNECT_TO_VAR = 5

logger = logging.getLogger('flud.comm')

class BadCASKeyException(failure.DefaultException):
    pass

class NotFoundException(failure.DefaultException):
    pass

class BadRequestException(failure.DefaultException):
    pass


i = 0
"""
Some utility functions used by both client and server.
"""
def updateNodes(client, config, nodes):
    if nodes and not isinstance(nodes, list) and not isinstance(nodes, tuple):
        raise TypeError("updateNodes must be called with node list, tuple,"
                " or kData dict")
    logger.debug("updateNodes(%s)" % nodes)
    for i in nodes:
        host = i[0]
        port = i[1]
        nID = i[2]
        nKu = FludRSA.importPublicKey(i[3])
        updateNode(client, config, host, port, nKu, nID)

updateNodePendingGETID = {}
def updateNode(client, config, host, port, nKu=None, nID=None):
    """
    Updates this node's view of the given node.  This includes updating
    the known-nodes record, trust, and routing table information
    """
    def updateNodeFail(failure, host, port):
        logging.getLogger('flud').log(logging.INFO,
                "couldn't get nodeID from %s:%d: %s" % (host, port, failure))

    def callUpdateNode(nKu, client, config, host, port, nID):
        return updateNode(client, config, host, port, nKu, nID)

    if isinstance(nID, int):
        nID = "%064x" % nID

    if nKu is None:
        #print "updateNode, no nKu"
        if nID is None:
            d = client.node.async_runtime.deferred_from_coro(
                    client.get_id(host, port))
            d.addCallback(callUpdateNode, client, config, host, port, nID)
            d.addErrback(updateNodeFail, host, port)
        else:
            #print "updateNode, no nKu but got a nID"
            if nID in config.nodes:
                return updateNode(client, config, host, port, 
                        FludRSA.importPublicKey(config.nodes[nID]['Ku']), nID)
            elif nID in updateNodePendingGETID:
                pass
            else:
                #print "updateNode, sending GETID"
                updateNodePendingGETID[nID] = True
                d = client.node.async_runtime.deferred_from_coro(
                        client.get_id(host, port))
                d.addCallback(callUpdateNode, client, config, host, port, nID)
                d.addErrback(updateNodeFail, host, port)
    elif isinstance(nKu, FludRSA):
        #print "updateNode with nKu"
        if nID in updateNodePendingGETID:
            del updateNodePendingGETID[nID]
        if nID == None:
            nID = nKu.id()
        elif nID != nKu.id():
            raise ValueError("updateNode: given nID doesn't match given nKu."
                    " '%s' != '%s'" % (nID, nKu.id()))
            # XXX: looks like an imposter -- instead of raising, mark host:port
            # pair as bad (trust-- on host:port alone, since we don't know id).
        if (nID in config.nodes) == False:
            config.addNode(nID, host, port, nKu)
        # XXX: trust
        # routing
        node = (host, port, int(nID, 16), nKu.exportPublicKey()['n'])
        replacee = config.routing.updateNode(node)
        #logger.info("knownnodes now: %s" % config.routing.knownNodes())
        #print "knownnodes now: %s" % config.routing.knownNodes()
        if replacee != None:
            logging.getLogger('flud').info(
                    "determining if replacement in ktable is needed")
            replaceNode(None, config.routing, replacee, node)
    else:
        #print "updateNode nKu=%s, type=%s" % (nKu, type(nKu))
        logging.getLogger('flud').warn( 
                "updateNode can't update without a public key or nodeID")
        frame = inspect.currentframe()
        # XXX: try/except here for debugging only
        try:
            stack = inspect.stack()
            for i in stack:
                print("from %s:%d" % (i[1], i[2]))
        except:
            print("couldn't get stack trace")
        raise ValueError("updateNode needs an nKu of type FludRSA"
            " (received %s) or an nID of type long or str (received %s)" 
            % (type(nKu), type(nID)))
        # XXX: should really make it impossible to call without one of these...

def replaceNode(error, routing, replacee, replacer):
    routing.replaceNode(replacee, replacer) 
    print("replaced node in ktable")

def requireParams(request, paramNames):
    # Looks for the named parameters in request.  If found, returns
    # a dict of param/value mappings.  If any named parameter is missing,
    # raises an exception
    params = {}
    for i in paramNames:
        try:
            key = i
            if key not in request.args and isinstance(key, str):
                key = key.encode("utf-8")
            val = request.args[key][0]
            if isinstance(val, bytes):
                val = val.decode("utf-8")
            params[i] = val
        except:
            raise Exception("missing parameter '"+i+"'") #XXX: use cust Exc
    return params

def getCanonicalIP(IP):
    # Preserve loopback targets as loopback. Rewriting localhost to the
    # machine FQDN can point at a non-listening interface (for example Mac.lan).
    local_fqdn = socket.getfqdn()
    if isinstance(IP, str) and IP.lower() == local_fqdn.lower():
        return '127.0.0.1'
    if IP in ('127.0.0.1', 'localhost', '::1'):
        return '127.0.0.1'
    else:
        return socket.getfqdn(IP)

class ImposterException(FludException):
    pass
