"""
ClientPrimitives.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

Primitive client storage protocol
"""

from http import HTTPStatus
import binascii
import time, os, stat, sys, logging, tarfile, gzip, asyncio, socket
from io import StringIO, BytesIO
import threading
import itertools

from flud.FludCrypto import FludRSA
from flud.fencode import fencode, fdecode
from flud.async_runtime import maybe_await

from .FludCommUtil import *

try:
    import aiohttp
except Exception:  # pragma: no cover - aiohttp is optional at runtime
    aiohttp = None


logger = logging.getLogger("flud.client.op")
loggerid = logging.getLogger("flud.client.op.id")
loggerstor = logging.getLogger("flud.client.op.stor")
loggerstoragg = logging.getLogger("flud.client.op.stor.agg")
loggerrtrv = logging.getLogger("flud.client.op.rtrv")
loggerdele = logging.getLogger("flud.client.op.dele")
loggervrfy = logging.getLogger("flud.client.op.vrfy")
loggerauth = logging.getLogger("flud.client.op.auth")


def _async_diag_enabled():
    return os.environ.get("FLUD_ASYNC_DIAG") == "1"


async def _run_on_node_runtime(node, coro):
    return await maybe_await(node.async_runtime.submit(coro))


async def send_get_id(node, host, port):
    return await _run_on_node_runtime(node, _send_get_id(node, host, port))


async def _send_get_id(node, host, port):
    host = getCanonicalIP(host)
    Ku = node.config.Ku.exportPublicKey()
    url = "http://%s:%d/ID?nodeID=%s&port=%s&Ku_e=%s&Ku_n=%s" % (
            host, port, node.config.nodeID, node.config.port, Ku['e'], Ku['n'])
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    for timeoutcount in range(MAXTIMEOUTS):
        try:
            timeout = aiohttp.ClientTimeout(total=primitive_to)
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
                        "SENDGETID FAILED to %s:%d: server sent status %s, '%s'"
                        % (host, port, status, body))
            try:
                nKu = FludRSA.importPublicKey(eval(body))
            except Exception:
                raise RuntimeError(
                        "SENDGETID FAILED to %s:%d: received invalid key"
                        % (host, port))
            updateNode(node.client, node.config, host, port, nKu)
            loggerid.info("SENDGETID PASSED to %s:%d", host, port)
            return nKu
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            if timeoutcount + 1 >= MAXTIMEOUTS:
                raise socket.error(str(exc))


def _build_store_form(datafile, metadata, params, skipfile):
    data = aiohttp.FormData()
    params_local = list(params)
    files = []
    if skipfile:
        files = [(None, 'filename')]
    elif metadata:
        metakey = metadata[0]
        params_local.append(('metakey', metakey))
        metafile = metadata[1]
        files = [(datafile, 'filename'), (metafile, 'meta')]
    else:
        files = [(datafile, 'filename')]

    for (param, value) in params_local:
        data.add_field(param, str(value))

    for fileobj, element in files:
        if fileobj is None:
            data.add_field(element, b"", filename="null",
                    content_type="application/octet-stream")
            continue
        if hasattr(fileobj, "read"):
            fileobj.seek(0, 2)
            fileobj.seek(0, 0)
            file_bytes = fileobj.read()
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            data.add_field(element, file_bytes, filename=element,
                    content_type="application/octet-stream")
            continue
        with open(fileobj, "rb") as fhandle:
            file_bytes = fhandle.read()
        data.add_field(element, file_bytes,
                filename=os.path.basename(fileobj),
                content_type="application/octet-stream")
    return data


async def send_store_request(nKu, node, host, port, datafile, metadata=None):
    return await _run_on_node_runtime(
            node, _send_store_request(nKu, node, host, port, datafile, metadata))


async def _send_store_request(nKu, node, host, port, datafile, metadata=None):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async STORE")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    fsize = os.stat(datafile)[stat.ST_SIZE]
    Ku = node.config.Ku.exportPublicKey()
    filekey = os.path.basename(datafile)
    params = [('nodeID', node.config.nodeID),
            ('Ku_e', str(Ku['e'])),
            ('Ku_n', str(Ku['n'])),
            ('port', str(node.config.port)),
            ('size', str(fsize))]
    url = "http://%s:%d/file/%s" % (host, port, filekey)
    timeoutcount = 0
    while True:
        try:
            auth_retries = 0
            hdrs = dict(headers)
            while True:
                if _async_diag_enabled():
                    loggerstor.warning("SENDSTORE async POST %s skip=%s",
                            url, False)
                timeout = aiohttp.ClientTimeout(total=primitive_to)
                resp = await node.async_http.request(
                        "POST", url,
                        data=_build_store_form(datafile, metadata, params, False),
                        headers=_normalize_headers(hdrs),
                        timeout=timeout)
                try:
                    status = resp.status
                    reason = resp.reason
                    body = await resp.read()
                finally:
                    resp.release()
                if _async_diag_enabled():
                    loggerstor.warning("SENDSTORE async response %s %s %s",
                            status, reason, url)
                if status == HTTPStatus.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise RuntimeError(
                                "SENDSTORE unauthorized (retries exhausted)")
                    challenge = None
                    if body:
                        challenge = body.decode("utf-8", errors="ignore")
                    if not challenge:
                        challenge = reason
                    hdrs = answerChallenge(challenge, node.config.Kr,
                            node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == HTTPStatus.CONFLICT:
                    raise BadCASKeyException("%s %s" % (status, reason))
                if status != HTTPStatus.OK:
                    raise RuntimeError(
                            "received %s in SENDSTORE response: %s"
                            % (status, body))
                updateNode(node.client, node.config, host, port, nKu)
                loggerstor.info("received SENDSTORE response from %s:%d: %s",
                        host, port, str(body))
                return body
        except BadCASKeyException:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))
            loggerstor.info("retrying async SENDSTORE [#%d] to %s:%d",
                    timeoutcount, host, port)


async def aggregate_store(nKu, node, host, port, datafile, metadata=None):
    request = AggregateStore(nKu, node, host, port, datafile, metadata)
    return await request.run()


async def send_retrieve(nKu, node, host, port, filekey, metakey=True):
    return await _run_on_node_runtime(
            node, _send_retrieve(nKu, node, host, port, filekey, metakey))


async def _send_retrieve(nKu, node, host, port, filekey, metakey=True):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async RETRIEVE")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    Ku = node.config.Ku.exportPublicKey()
    url = ('http://%s:%d/file/%s?nodeID=%s&port=%s&Ku_e=%s&Ku_n=%s'
           '&metakey=%s') % (
            host, port, filekey, node.config.nodeID, node.config.port,
            Ku['e'], Ku['n'], metakey)
    timeoutcount = 0
    while True:
        try:
            auth_retries = 0
            hdrs = dict(headers)
            while True:
                timeout = aiohttp.ClientTimeout(total=transfer_to)
                resp = await node.async_http.request(
                        "GET", url,
                        headers=_normalize_headers(hdrs),
                        timeout=timeout)
                try:
                    status = resp.status
                    reason = resp.reason
                    body = await resp.read()
                    content_type = resp.headers.get("Content-Type", "")
                    boundary = resp.headers.get("boundary", "")
                finally:
                    resp.release()
                if status == HTTPStatus.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise RuntimeError(
                                "SENDRETRIEVE unauthorized (retries exhausted)")
                    challenge = body.decode("utf-8", errors="ignore") if body else ""
                    if not challenge:
                        challenge = reason
                    hdrs = answerChallenge(challenge, node.config.Kr,
                            node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == HTTPStatus.NOT_FOUND:
                    raise NotFoundException("Not found: %s" % filekey)
                if status == HTTPStatus.BAD_REQUEST:
                    raise BadRequestException("Bad request for %s" % filekey)
                if status != HTTPStatus.OK:
                    raise RuntimeError(
                            "SENDRETRIEVE FAILED: server sent status %s, '%s'"
                            % (status, body))
                saved = _save_retrieve_response(
                        body, content_type, node.config.clientdir, filekey, boundary)
                updateNode(node.client, node.config, host, port, nKu)
                return saved
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))


async def send_delete(nKu, node, host, port, filekey, metakey):
    return await _run_on_node_runtime(
            node, _send_delete(nKu, node, host, port, filekey, metakey))


async def _send_delete(nKu, node, host, port, filekey, metakey):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async DELETE")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    Ku = node.config.Ku.exportPublicKey()
    url = ('http://%s:%d/file/%s?nodeID=%s&port=%s&Ku_e=%s&Ku_n=%s'
           '&metakey=%s') % (
            host, port, filekey, node.config.nodeID, node.config.port,
            Ku['e'], Ku['n'], metakey)
    timeoutcount = 0
    while True:
        try:
            auth_retries = 0
            hdrs = dict(headers)
            while True:
                timeout = aiohttp.ClientTimeout(total=primitive_to)
                resp = await node.async_http.request(
                        "DELETE", url,
                        headers=_normalize_headers(hdrs),
                        timeout=timeout)
                try:
                    status = resp.status
                    reason = resp.reason
                    body = await resp.text()
                finally:
                    resp.release()
                if status == HTTPStatus.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise RuntimeError(
                                "SENDDELETE unauthorized (retries exhausted)")
                    challenge = body or reason
                    hdrs = answerChallenge(challenge, node.config.Kr,
                            node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == HTTPStatus.NOT_FOUND:
                    raise NotFoundException(body or "not found")
                if status == HTTPStatus.BAD_REQUEST:
                    raise BadRequestException(body or "bad request")
                if status != HTTPStatus.OK:
                    raise RuntimeError(
                            "SENDDELETE FAILED: server sent status %s, '%s'"
                            % (status, body))
                updateNode(node.client, node.config, host, port, nKu)
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))


async def send_verify(nKu, node, host, port, filename, offset, length,
        meta=None):
    return await _run_on_node_runtime(
            node,
            _send_verify(nKu, node, host, port, filename, offset, length, meta))


async def _send_verify(nKu, node, host, port, filename, offset, length,
        meta=None):
    if aiohttp is None:
        raise RuntimeError("aiohttp not available for async VERIFY")
    host = getCanonicalIP(host)
    headers = {'Fludprotocol': PROTOCOL_VERSION, 'User-Agent': 'FludClient'}
    filekey = os.path.basename(filename)
    Ku = node.config.Ku.exportPublicKey()
    url = ('http://%s:%d/hash/%s?nodeID=%s&port=%s&Ku_e=%s&Ku_n=%s'
           '&offset=%s&length=%s') % (
            host, port, filekey, node.config.nodeID, node.config.port,
            Ku['e'], Ku['n'], offset, length)
    if meta:
        url += "&metakey=%s&meta=%s" % (meta[0], fencode(meta[1].read()))
    timeoutcount = 0
    while True:
        try:
            auth_retries = 0
            hdrs = dict(headers)
            while True:
                timeout = aiohttp.ClientTimeout(total=primitive_to)
                resp = await node.async_http.request(
                        "GET", url,
                        headers=_normalize_headers(hdrs),
                        timeout=timeout)
                try:
                    status = resp.status
                    reason = resp.reason
                    body = await resp.text()
                finally:
                    resp.release()
                if status == HTTPStatus.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise RuntimeError(
                                "SENDVERIFY unauthorized (retries exhausted)")
                    challenge = body or reason
                    hdrs = answerChallenge(challenge, node.config.Kr,
                            node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == HTTPStatus.NOT_FOUND:
                    raise NotFoundException(body or "not found")
                if status == HTTPStatus.BAD_REQUEST:
                    raise BadRequestException(body or "bad request")
                if status != HTTPStatus.OK:
                    raise RuntimeError(
                            "SENDVERIFY FAILED: server sent status %s, '%s'"
                            % (status, body))
                updateNode(node.client, node.config, host, port, nKu)
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            timeoutcount += 1
            if timeoutcount >= MAXTIMEOUTS:
                raise socket.error(str(exc))

MINSTORSIZE = 512000  # anything smaller than this tries to get aggregated
TARFILE_TO = 2        # timeout for checking aggregated tar files

MAXAUTHRETRY = 4      # number of times to retry auth

# FUTURE: check flud protocol version for backwards compatibility
# XXX: need to make sure we have appropriate timeouts for all comms.
# FUTURE: DOS attacks.  For now, assume that network hardware can filter these 
#      out (by throttling individual IPs) -- i.e., it isn't our problem.  If we
#      want to defend against this at some point, we need to keep track of who
#      is generating requests and then ignore them.
# XXX: might want to consider some self-healing for the kademlia layer, as 
#      outlined by this thread: 
#      http://zgp.org/pipermail/p2p-hackers/2003-August/001348.html (should also
#      consider Zooko's links in the parent to this post)
# XXX: disallow requests to self.

def _normalize_headers(headers):
    norm_headers = {}
    for key, value in headers.items():
        if isinstance(key, bytes):
            key = key.decode("ascii", errors="strict")
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="strict")
        norm_headers[str(key)] = str(value)
    return norm_headers


def _save_retrieve_response(body, content_type, target_dir, filekey,
        boundary_header=None):
    content_type = content_type or "application/octet-stream"
    parts = [p.strip() for p in content_type.split(";") if p.strip()]
    ctype = parts[0] if parts else "application/octet-stream"
    params = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        params[key.strip().lower()] = value.strip().strip('"')
    ctype = ctype.lower()
    boundary = params.get("boundary")
    if not boundary and boundary_header:
        boundary = str(boundary_header).strip().strip('"')
    saved = []

    if ctype.startswith("multipart/") and boundary:
        marker = ("--%s" % boundary).encode("utf-8")
        for part in body.split(marker):
            if not part:
                continue
            if part.startswith(b"--"):
                # terminating multipart boundary marker
                continue
            if part.startswith(b"\r\n"):
                part = part[2:]
            if not part:
                continue
            if part.endswith(b"\r\n"):
                part = part[:-2]
            header_blob, sep, payload = part.partition(b"\r\n\r\n")
            if not sep:
                continue
            headers = {}
            for line in header_blob.split(b"\r\n"):
                if b":" not in line:
                    continue
                k, v = line.split(b":", 1)
                headers[k.strip().lower()] = v.strip()
            content_id = headers.get(b"content-id")
            if not content_id:
                continue
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]
            content_id = content_id.decode("utf-8", errors="replace").strip()
            filename = os.path.join(target_dir, content_id)
            with open(filename, "wb") as f:
                f.write(payload)
            saved.append(filename)

    if saved:
        return saved

    filename = os.path.join(target_dir, filekey)
    with open(filename, "wb") as f:
        f.write(body)
    return [filename]

aggregate_waiters = {}  # a map of maps, containing waiter futures.  The
                        # waiters for file 'x' in tarball 'y' are accessed as
                        # aggregate_waiters['y']['x']
aggTimeoutMap = {}   # a map of timout calls for a tarball.  The timeout for
                     # tarball 'y' is stored in aggTimeoutMap['y']
aggStateLock = threading.Lock()
aggGeneration = itertools.count(1)
def _resolve_waiter(waiter, result):
    loop = waiter.get_loop()
    loop.call_soon_threadsafe(waiter.set_result, result)


def _reject_waiter(waiter, failure):
    loop = waiter.get_loop()
    loop.call_soon_threadsafe(waiter.set_exception, failure)


class AggregateStore:

    # XXX: if multiple guys store the same file, we're going to get into bad
    # completion state (the except clause in failTarfiles).  Need to catch this
    # as it happens... (this happens e.g. for small files with the same
    # filehash, e.g, 0-byte files, file copies etc).  Should fix this in
    # FludClient -- non-aggregated store has a similar problem (encoded file
    # chunks get deleted out from under successive STOR ops for the same
    # chunk, i.e. from two concurrent STORs of the same file contents)
    def __init__(self, nKu, node, host, port, datafile, metadata):
        self.nKu = nKu
        self.node = node
        self.host = host
        self.port = port
        self.datafile = datafile
        self.metadata = metadata
        tarbase = os.path.join(node.config.clientdir, nKu.id()) \
                + '-' + host + '-' + str(port)
        tarfilename = tarbase + ".tar"
        loggerstoragg.debug("tarfile name is %s" % tarfilename)
        with aggStateLock:
            if tarfilename in aggregate_waiters and not os.path.exists(tarfilename):
                tarfilename = "%s.%d.tar" % (tarbase, next(aggGeneration))
                loggerstoragg.debug("using fresh tarfile generation %s",
                        tarfilename)
            create_tar = not os.path.exists(tarfilename) \
                    or tarfilename not in aggregate_waiters
            if create_tar:
                loggerstoragg.debug("creating tarfile %s to append %s"
                        % (tarfilename, datafile))
                tar = tarfile.open(tarfilename, "w")
                aggregate_waiters[tarfilename] = {}
            else:
                loggerstoragg.debug("opening tarfile %s to append %s"
                        % (tarfilename, datafile))
                tar = tarfile.open(tarfilename, "a")
            try:
                if os.path.basename(datafile) not in tar.getnames():
                    loggerstoragg.info("adding datafile %s to tarball, %s"
                            % (os.path.basename(datafile), tar.getnames()))
                    loggerstoragg.debug("adding data to tarball")
                    tar.add(datafile, os.path.basename(datafile))
                else:
                    loggerstoragg.info("skip adding datafile %s to tarball"
                            % datafile)

                if metadata:
                    metafilename = "%s.%s.meta" % (os.path.basename(datafile),
                            metadata[0])
                    loggerstoragg.debug("metadata filename is %s" % metafilename)
                    try:
                        if isinstance(metadata[1], StringIO):
                            loggerstoragg.debug("metadata is StringIO")
                            tinfo = tarfile.TarInfo(metafilename)
                            meta_bytes = metadata[1].getvalue()
                            if isinstance(meta_bytes, str):
                                meta_bytes = meta_bytes.encode("utf-8")
                            metaio = BytesIO(meta_bytes)
                            tinfo.size = len(meta_bytes)
                            tar.addfile(tinfo, metaio)
                        elif isinstance(metadata[1], BytesIO):
                            loggerstoragg.debug("metadata is BytesIO")
                            tinfo = tarfile.TarInfo(metafilename)
                            metadata[1].seek(0,2)
                            tinfo.size = metadata[1].tell()
                            metadata[1].seek(0,0)
                            tar.addfile(tinfo, metadata[1])
                        else:
                            loggerstoragg.debug("metadata is file")
                            tar.add(metadata[1], metafilename)
                    except:
                        import traceback
                        loggerstoragg.debug("exception while adding metadata to"
                                " tarball")
                        print(sys.exc_info()[2])
                        traceback.print_exc()
            finally:
                tar.close()

            loggerstoragg.debug("prepping waiter future")
            waiter = asyncio.get_running_loop().create_future()
            self.future = waiter
            loggerstoragg.debug("adding waiter on %s for %s"
                    % (tarfilename, datafile))
            try:
                aggregate_waiters[tarfilename][os.path.basename(datafile)].append(
                        waiter)
            except KeyError:
                aggregate_waiters[tarfilename][os.path.basename(datafile)] \
                        = [waiter]
        self.resetTimeout(tarfilename, nKu, node, host, port)

    async def run(self):
        return await self.future

    def resetTimeout(self, tarball, nKu, node, host, port):
        loggerstoragg.debug("in resetTimeout...")
        self._resetAsyncTimeout(tarball, nKu, node, host, port)

    def _resetAsyncTimeout(self, tarball, nKu, node, host, port):
        runtime = node.async_runtime
        if not os.path.exists(tarball):
            return

        def _schedule():
            handle = aggTimeoutMap.get(tarball)
            if handle is not None:
                handle.cancel()
            should_delay = os.path.exists(tarball) and \
                    os.stat(tarball)[stat.ST_SIZE] < MINSTORSIZE
            delay = TARFILE_TO if should_delay else 0
            aggTimeoutMap[tarball] = runtime.loop.call_later(
                    delay,
                    lambda: runtime.submit(
                        self._sendTarAsync(tarball, nKu, node, host, port)))

        runtime.loop.call_soon_threadsafe(_schedule)

    def _prepareTarball(self, tarball):
        work_tarball = tarball + ".sending"
        with aggStateLock:
            if not os.path.exists(tarball):
                raise FileNotFoundError(tarball)
            if os.path.exists(work_tarball):
                os.remove(work_tarball)
            os.rename(tarball, work_tarball)
        gtarball = tarball+".gz"
        gtar = gzip.GzipFile(gtarball, 'wb')
        try:
            with open(work_tarball, 'rb') as src:
                gtar.write(src.read())
        finally:
            gtar.close()
        os.remove(work_tarball)
        return gtarball
        
    async def _sendTarAsync(self, tarball, nKu, node, host, port):
        loggerstoragg.info(
                "aggregation op triggered, sending tarfile %s.gz to %s:%d (async)"
                % (tarball, host, port))
        try:
            gtarball = await asyncio.to_thread(self._prepareTarball, tarball)
            result = await _send_store_request(nKu, node, host, port, gtarball)
        except Exception as exc:
            self.failTarfiles(exc, tarball)
            return None
        self.completeTarfiles(result, tarball)
        return result

    # XXX: make aggregate_waiters use a non-.tar key, so that we don't have to
    # keep passing 'tarball' around (since we removed it and are really only
    # interested in gtarball now, use gtarball at the least)
    def completeTarfiles(self, result, tarball):
        loggerstoragg.debug("completeTarfiles")
        gtarball = tarball+".gz"
        tar = tarfile.open(gtarball, "r:gz")
        waiters = []
        try: 
            for tarinfo in tar:
                if tarinfo.name[-5:] != '.meta':
                    waiter_list = aggregate_waiters[tarball].pop(tarinfo.name) 
                    loggerstoragg.debug("completing %s in %s (%d waiters)" 
                            % (tarinfo.name, tarball, len(waiter_list)))
                    waiters.extend(waiter_list)
        except KeyError:
            loggerstoragg.warning("aggregate_waiters has keys: %s" 
                    % str(list(aggregate_waiters.keys())))
            loggerstoragg.warning("aggregate_waiters[%s] has keys: %s" % (tarball, 
                    str(list(aggregate_waiters[tarball].keys()))))
        tar.close()
        with aggStateLock:
            aggregate_waiters.pop(tarball, None)
            handle = aggTimeoutMap.pop(tarball, None)
        if handle is not None and hasattr(handle, "cancel"):
            try:
                handle.cancel()
            except Exception:
                pass
        loggerstoragg.debug("deleting tarball %s" % gtarball)
        os.remove(gtarball)
        for waiter in waiters:
            _resolve_waiter(waiter, result)

    def failTarfiles(self, failure, tarball):
        loggerstoragg.debug("failTarfiles")
        gtarball = tarball+".gz"
        tar = tarfile.open(gtarball, "r:gz")
        waiters = []
        try: 
            for tarinfo in tar:
                waiter_list = aggregate_waiters[tarball].pop(tarinfo.name) 
                loggerstoragg.debug("failing %s in %s (%d waiters)"
                        % (tarinfo.name, tarball, len(waiter_list)))
                waiters.extend(waiter_list)
        except KeyError:
            loggerstoragg.warning("aggregate_waiters has keys: %s" 
                    % str(list(aggregate_waiters.keys())))
            loggerstoragg.warning("aggregate_waiters[%s] has keys: %s" % (tarball, 
                    str(list(aggregate_waiters[tarball].keys()))))
        tar.close()
        with aggStateLock:
            aggregate_waiters.pop(tarball, None)
            handle = aggTimeoutMap.pop(tarball, None)
        if handle is not None and hasattr(handle, "cancel"):
            try:
                handle.cancel()
            except Exception:
                pass
        loggerstoragg.debug("NOT deleting tarball %s (for debug)" % gtarball)
        #os.remove(gtarball)
        for waiter in waiters:
            _reject_waiter(waiter, failure)

def _normalize_challenge(challenge):
    if isinstance(challenge, bytes):
        challenge = challenge.decode("utf-8", errors="replace")
    challenge = str(challenge).strip()
    lower = challenge.lower()
    if lower.startswith("challenge"):
        parts = challenge.split("=", 1)
        if len(parts) == 2:
            challenge = parts[1].strip()
    return challenge

def answerChallenge(challenge, Kr, groupIDu, sID, headers={}):
    loggerauth.debug("got challenge: '%s'" % challenge)
    challenge = _normalize_challenge(challenge)
    loggerauth.debug("normalized challenge: '%s'" % challenge)
    sID = binascii.unhexlify(sID)
    challenge = (fdecode(challenge),)
    response = fencode(Kr.decrypt(challenge))
    # XXX: RSA.decrypt won't restore leading 0's.  This causes
    #      some challenges to fail when they shouldn't -- solved for now
    #      on the server side by generating non-0 leading challenges.
    loggerauth.debug("decrypted challenge to %s" % response)
    responseID = fdecode(response)[:len(sID)]
    loggerauth.debug("  response id: %s" % fencode(responseID))
    if responseID != sID:
        # fail the op.
        # If we don't do this, we may be allowing the server to build a
        # dictionary useful for attack.  The attack is as follows: node A
        # (server) collects a bunch of un-IDed challenge/response pairs by
        # issuing challenges to node B (client).  Then node A uses those
        # responses to pose as B to some other server C.  This sounds
        # farfetched, in that such a database would need to be huge, but in
        # reality, such an attack can happen in real-time, with node A
        # simultaneously serving requests from B, relaying challenges from C to
        # B, and then responding with B's responses to C to gain resources
        # there as an imposter.  The ID string prevents this attack.

        # XXX: trust-- (must go by ip:port, since ID could be innocent)
        raise ImposterException("node %s is issuing invalid challenges --"
                " claims to have id=%s" % (fencode(sID), fencode(responseID)))
    response = fdecode(response)[len(sID):]
    loggerauth.debug("  challenge response: '%s'" % fencode(response))
    response = fencode(response)+":"+groupIDu
    loggerauth.debug("response:groupIDu=%s" % response)
    if isinstance(response, str):
        response = response.encode("utf-8")
    response = binascii.b2a_base64(response)
    loggerauth.debug("b64(response:groupIDu)=%s" % response)
    response = b"Basic " + response.strip()
    headers['Authorization'] = response
    return headers 
