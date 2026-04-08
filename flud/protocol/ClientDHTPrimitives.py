"""
ClientDHTPrimitives.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

Primitive client DHT protocol
"""
import time, logging, asyncio, socket
from http import HTTPStatus
import flud.defer as defer
import flud.FludkRouting as FludkRouting
from flud.fencode import fencode
from flud.async_runtime import maybe_await

from . import ConnectionQueue
from .ClientPrimitives import REQUEST, _normalize_headers
from .FludCommUtil import *

try:
    import aiohttp
except Exception:  # pragma: no cover - aiohttp is optional at runtime
    aiohttp = None


logger = logging.getLogger("flud.client.dht")

# FUTURE: check flud protocol version for backwards compatibility
# XXX: need to make sure we have appropriate timeouts for all comms.
# FUTURE: DOS attacks.  For now, assume that network hardware can filter these 
#      out (by throttling individual IPs) -- i.e., it isn't our problem.  If we
#      want to defend against this at some point, we need to keep track of who
#      is generating requests and then ignore them.
# XXX: might want to consider some self-healing for the kademlia layer, as 
#      outlined by this thread: 
#      http://zgp.org/pipermail/p2p-hackers/2003-August/001348.html (should also
#      consider Zooko's links in the parent to this post).  Basic idea: don't
#      always take the k-closest -- take x random and k-x of the k-closest.
#      Can alternate each round (k-closest / x + k-x-closest) for a bit more
#      diversity (as in "Sybil-resistent DHT routing").
# XXX: right now, calls to updateNode are chained.  Might want to think about
#      doing some of this more asynchronously, so that the recursive parts
#      aren't waiting for remote GETIDs to return before recursing.

"""
The active DHT client path is asyncio-native.  Single-node SEND* request
classes live here, and the async_k* helpers compose them into recursive
operations.
"""


async def send_kfindnode(node, host, port, key, command_name="nodes"):
    return await maybe_await(
            node.async_runtime.deferred_from_coro(
                _send_kfindnode(node, host, port, key, command_name)))


async def _send_kfindnode(node, host, port, key, command_name="nodes"):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async DHT request")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    Ku = node.config.Ku.exportPublicKey()
    url = ('http://%s:%d/%s/%s?nodeID=%s&Ku_e=%s&Ku_n=%s&port=%s') % (
            host, port, command_name, fencode(key), node.config.nodeID,
            Ku['e'], Ku['n'], node.config.port)
    timeoutcount = 0
    while True:
        try:
            timeout = aiohttp.ClientTimeout(total=kprimitive_to)
            resp = await node.async_http.request(
                    "GET", url,
                    headers=_normalize_headers(headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
            finally:
                resp.release()
            if status != HTTPStatus.OK:
                raise RuntimeError(
                        "%s FAILED from %s:%d: received status %s, '%s'"
                        % (command_name, host, port, status, body))
            response = eval(body)
            nID = int(response['id'], 16)
            updateNode(node.client, node.config, host, port, None, nID)
            updateNodes(node.client, node.config, response['k'])
            return response
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))


async def send_kfindvalue(node, host, port, key):
    return await maybe_await(
            node.async_runtime.deferred_from_coro(
                _send_kfindvalue(node, host, port, key)))


async def _send_kfindvalue(node, host, port, key):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async DHT request")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    Ku = node.config.Ku.exportPublicKey()
    url = ('http://%s:%d/meta/%s?nodeID=%s&Ku_e=%s&Ku_n=%s&port=%s') % (
            host, port, fencode(key), node.config.nodeID,
            Ku['e'], Ku['n'], node.config.port)
    timeoutcount = 0
    while True:
        try:
            timeout = aiohttp.ClientTimeout(total=kprimitive_to)
            resp = await node.async_http.request(
                    "GET", url,
                    headers=_normalize_headers(headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
                content_type = resp.headers.get("Content-Type", "")
                node_id = resp.headers.get("nodeID")
            finally:
                resp.release()
            if status != HTTPStatus.OK:
                raise RuntimeError(
                        "meta FAILED from %s:%d: received status %s, '%s'"
                        % (host, port, status, body))
            if content_type == "application/x-flud-data":
                updateNode(node.client, node.config, host, port, None, node_id)
                return body
            response = eval(body)
            nID = int(response['id'], 16)
            updateNode(node.client, node.config, host, port, None, nID)
            updateNodes(node.client, node.config, response['k'])
            return response
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))


async def send_kstore(node, host, port, key, val):
    return await maybe_await(
            node.async_runtime.deferred_from_coro(
                _send_kstore(node, host, port, key, val)))


async def _send_kstore(node, host, port, key, val):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async kSTORE")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    Ku = node.config.Ku.exportPublicKey()
    url = ('http://%s:%d/meta/%s/%s?nodeID=%s&Ku_e=%s&Ku_n=%s&port=%s') % (
            host, port, fencode(key), fencode(val), node.config.nodeID,
            Ku['e'], Ku['n'], node.config.port)
    timeoutcount = 0
    while True:
        try:
            timeout = aiohttp.ClientTimeout(total=kprimitive_to)
            resp = await node.async_http.request(
                    "PUT", url,
                    headers=_normalize_headers(headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
            finally:
                resp.release()
            if status != HTTPStatus.OK:
                raise RuntimeError(
                        "kSTORE FAILED from %s:%d status=%s body=%s"
                        % (host, port, status, body))
            logger.info("kSTORE to %s:%d finished", host, port)
            return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))


async def async_kFindNode(node, key):
    node.DHTtstamp = time.time()
    queried = {}
    outstanding = set()
    pending = []
    kclosest = []
    abbrvkey = ("%x" % key)[:8] + "..."
    abbrv = "(%s%s)" % (abbrvkey, str(node.DHTtstamp)[-7:])

    def _update_state(response, host, port):
        if not isinstance(response, dict):
            return response
        if len(response['k']) == 1 and response['k'][0][2] == key:
            if response['k'][0] not in kclosest:
                kclosest.insert(0, response['k'][0])
                del kclosest[FludkRouting.k:]
            return response

        responder_id = int(response['id'], 16)
        outstanding.discard((host, port, responder_id))
        queried[responder_id] = (host, port)

        for candidate in response['k']:
            node_tuple = (candidate[0], candidate[1], candidate[2])
            if candidate[2] not in queried and \
                    node_tuple not in pending and \
                    node_tuple not in outstanding:
                pending.append(node_tuple)
            if candidate not in kclosest:
                kclosest.append(candidate)
        kclosest.sort(key=lambda n, t=key: t ^ n[2])
        del kclosest[FludkRouting.k:]

        pending[:] = list(set(pending) - outstanding)
        for responder_id, responder_hostport in queried.items():
            node_tuple = (responder_hostport[0], responder_hostport[1], responder_id)
            if node_tuple in pending:
                pending.remove(node_tuple)
        pending.sort(key=lambda n, t=key: t ^ n[2])
        return None

    localhost = getCanonicalIP('localhost')
    local_response = {
        'id': node.config.nodeID,
        'k': node.config.routing.findNode(key),
    }
    exact = _update_state(local_response, localhost, node.config.port)
    if exact is not None:
        return exact

    round_no = 0
    while pending or outstanding:
        batch = pending[:FludkRouting.a]
        pending[:] = pending[len(batch):]
        if not batch:
            break
        logger.debug("FN: %s doing async round %d", abbrv, round_no)
        round_no += 1

        async def _query_one(host, port, node_id):
            outstanding.add((host, port, node_id))
            try:
                response = await send_kfindnode(node, host, port, key)
                return response, host, port
            finally:
                outstanding.discard((host, port, node_id))

        results = await asyncio.gather(
            *(_query_one(host, port, node_id) for host, port, node_id in batch),
            return_exceptions=True,
        )
        for item, result in zip(batch, results):
            host, port, node_id = item
            if isinstance(result, Exception):
                logger.info("kFindNode %s request to %s:%d failed -- %s",
                        abbrv, host, port, str(result))
                kclosest[:] = [
                    n for n in kclosest
                    if (n[0], n[1], n[2]) != (host, port, node_id)
                ]
                continue
            response, host, port = result
            exact = _update_state(response, host, port)
            if exact is not None:
                return exact

    logger.info("kFindNode %s terminated successfully after %d queries.",
            abbrv, len(queried))
    kclosest.sort(key=lambda n, t=key: t ^ n[2])
    return {'k': kclosest[:FludkRouting.k]}


async def async_kFindValue(node, key):
    node.DHTtstamp = time.time()
    queried = {}
    outstanding = set()
    pending = []
    kclosest = []
    done = False
    values = {}
    abbrvkey = ("%x" % key)[:8] + "..."
    abbrv = "(%s%s)" % (abbrvkey, str(node.DHTtstamp)[-7:])

    def _remember_value(response):
        values[response] = values.get(response, 0) + 1

    def _update_state(response, host, port):
        nonlocal done
        if not isinstance(response, dict):
            if response is not None:
                _remember_value(response)
            done = True
            pending[:] = []
            outstanding.clear()
            return response

        responder_id = int(response['id'], 16)
        queried[responder_id] = (host, port)
        for candidate in response['k']:
            node_tuple = (candidate[0], candidate[1], candidate[2])
            if candidate[2] not in queried and \
                    node_tuple not in pending and \
                    node_tuple not in outstanding:
                pending.append(node_tuple)
            if candidate not in kclosest:
                kclosest.append(candidate)
        kclosest.sort(key=lambda n, t=key: t ^ n[2])
        del kclosest[FludkRouting.k:]

        pending[:] = list(set(pending) - outstanding)
        for responder_id, responder_hostport in queried.items():
            node_tuple = (responder_hostport[0], responder_hostport[1], responder_id)
            if node_tuple in pending:
                pending.remove(node_tuple)
        pending.sort(key=lambda n, t=key: t ^ n[2])
        return None

    localhost = getCanonicalIP('localhost')
    initial = await send_kfindvalue(node, localhost, node.config.port, key)
    exact = _update_state(initial, localhost, node.config.port)
    if exact is not None and not isinstance(exact, dict):
        return exact

    round_no = 0
    while not done and (pending or outstanding):
        batch = pending[:FludkRouting.a]
        pending[:] = pending[len(batch):]
        if not batch:
            break
        logger.debug("FV: %s doing async round %d", abbrv, round_no)
        round_no += 1

        async def _query_one(host, port, node_id):
            outstanding.add((host, port, node_id))
            try:
                response = await send_kfindvalue(node, host, port, key)
                return response, host, port
            finally:
                outstanding.discard((host, port, node_id))

        results = await asyncio.gather(
            *(_query_one(host, port, node_id) for host, port, node_id in batch),
            return_exceptions=True,
        )
        for item, result in zip(batch, results):
            host, port, node_id = item
            if isinstance(result, Exception):
                logger.info("kFindValue %s request to %s:%d failed -- %s",
                        abbrv, host, port, str(result))
                kclosest[:] = [
                    n for n in kclosest
                    if (n[0], n[1], n[2]) != (host, port, node_id)
                ]
                continue
            response, host, port = result
            exact = _update_state(response, host, port)
            if exact is not None and not isinstance(exact, dict):
                return exact

    if not values:
        logger.info("couldn't get any results")
        return None
    return max(values.items(), key=lambda item: item[1])[0]


async def async_kStore(node, key, val):
    knodes = await async_kFindNode(node, key)
    knodes = knodes['k']
    if len(knodes) < 1:
        raise RuntimeError("can't complete kStore -- no nodes")
    results = await asyncio.gather(
        *(send_kstore(node, knode[0], knode[1], key, val)
          for knode in knodes),
        return_exceptions=True,
    )
    failures = [result for result in results if isinstance(result, Exception)]
    if failures:
        raise RuntimeError(results)
    logger.info("kStore finished")
    return ""

class SENDkFINDNODE_ASYNC(REQUEST):
    """
    Async aiohttp variant of SENDkFINDNODE.
    """
    def __init__(self, node, host, port, key, commandName="nodes"):
        logger.info("sending %s (findnode) for %s... to %s:%d (async)"
                % (commandName, ("%x" % key)[:10], host, port))
        self.commandName = commandName
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/'+self.commandName+'/'
        url += fencode(key)
        url += '?nodeID='+str(self.node.config.nodeID)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += '&port='+str(self.node.config.port)
        self.timeoutcount = 0
        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, node, host, port, key, url))

    def startRequest(self, node, host, port, key, url):
        d = self._sendRequest(node, host, port, key, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, node, host, port, key, url):
        deferred = self._run_async_request(
                self._async_request(node, host, port, key, url))
        deferred.addErrback(self._errSendk, node, host, port, key, url)
        return deferred

    async def _async_request(self, node, host, port, key, url):
        if aiohttp is None:
            raise RuntimeError(
                    "aiohttp not available for async DHT request")
        try:
            timeout = aiohttp.ClientTimeout(total=kprimitive_to)
            resp = await self._request(
                    "GET", url,
                    headers=_normalize_headers(self.headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
            finally:
                resp.release()
            if status != HTTPStatus.OK:
                raise RuntimeError(self.commandName+" FAILED from "
                        +host+":"+str(port)+": received status "
                        +str(status)+", '"+body+"'")
            response = eval(body)
            nID = int(response['id'], 16)
            updateNode(node.client, node.config, host, port, None, nID)
            updateNodes(node.client, node.config, response['k'])
            return response
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))

    def _errSendk(self, err, node, host, port, key, url):
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                return self._sendRequest(node, host, port, key, url)
            return err
        logger.info("%s to %s failed -- %s"
                % (self.commandName, self.dest, str(err)))
        return err


class SENDkSTORE_ASYNC(REQUEST):
    """
    Async aiohttp variant of SENDkSTORE.
    """
    def __init__(self, node, host, port, key, val):
        logger.info("sending kSTORE to %s:%d (async)" % (host, port))
        REQUEST.__init__(self, host, port, node)
        Ku = node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/meta/'
        url += fencode(key)+"/"+fencode(val)
        url += '?nodeID='+str(node.config.nodeID)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += '&port='+str(node.config.port)
        self.timeoutcount = 0
        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, host, port, url))

    def startRequest(self, host, port, url):
        d = self._sendRequest(host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, host, port, url):
        deferred = self._run_async_request(
                self._async_request(host, port, url))
        deferred.addErrback(self._storeErr, host, port, url)
        return deferred

    async def _async_request(self, host, port, url):
        if aiohttp is None:
            raise RuntimeError("aiohttp not available for async kSTORE")
        try:
            timeout = aiohttp.ClientTimeout(total=kprimitive_to)
            resp = await self._request(
                    "PUT", url,
                    headers=_normalize_headers(self.headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
            finally:
                resp.release()
            if status != HTTPStatus.OK:
                raise RuntimeError(
                        "kSTORE FAILED from %s:%d status=%s body=%s"
                        % (host, port, status, body))
            logger.info("kSTORE to %s:%d finished" % (host, port))
            return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))

    def _storeErr(self, err, host, port, url):
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                return self._sendRequest(host, port, url)
            return err
        logger.info("kSTORE to %s failed: %s" % (self.dest, str(err)))
        return err


class SENDkFINDVALUE_ASYNC(SENDkFINDNODE_ASYNC):
    """
    Async aiohttp variant of SENDkFINDVALUE.
    """
    def __init__(self, node, host, port, key):
        SENDkFINDNODE_ASYNC.__init__(self, node, host, port, key, "meta")

    async def _async_request(self, node, host, port, key, url):
        if aiohttp is None:
            raise RuntimeError(
                    "aiohttp not available for async DHT request")
        try:
            timeout = aiohttp.ClientTimeout(total=kprimitive_to)
            resp = await self._request(
                    "GET", url,
                    headers=_normalize_headers(self.headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
                content_type = resp.headers.get("Content-Type", "")
                node_id = resp.headers.get("nodeID")
            finally:
                resp.release()
            if status != HTTPStatus.OK:
                raise RuntimeError(self.commandName+" FAILED from "
                        +host+":"+str(port)+": received status "
                        +str(status)+", '"+body+"'")

            if content_type == "application/x-flud-data":
                logger.info("received SENDkFINDVALUE data.")
                updateNode(node.client, node.config, host, port, None, node_id)
                return body

            response = eval(body)
            nID = int(response['id'], 16)
            updateNode(node.client, node.config, host, port, None, nID)
            logger.info("received SENDkFINDVALUE nodes")
            logger.debug("received SENDkFINDVALUE nodes: %s" % response)
            updateNodes(node.client, node.config, response['k'])
            return response
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))
