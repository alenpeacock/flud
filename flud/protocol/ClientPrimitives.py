"""
ClientPrimitives.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

Primitive client storage protocol
"""

from twisted.web import http as twebhttp, client
from twisted.internet import reactor, threads, defer, error
from twisted.python import failure
import time, os, stat, sys, logging, tarfile, gzip, asyncio, socket
from io import StringIO, BytesIO
import threading

from flud.FludCrypto import FludRSA
from flud.fencode import fencode, fdecode
from flud.async_runtime import maybe_await

from . import ConnectionQueue
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

_warned_missing_aiohttp = False


def _use_async_http():
    global _warned_missing_aiohttp
    requested = os.environ.get("FLUD_ASYNCIO_CLIENT") == "1"
    if requested and aiohttp is None:
        if not _warned_missing_aiohttp:
            logger.warning("FLUD_ASYNCIO_CLIENT=1 set but aiohttp is unavailable; "
                    "falling back to Twisted HTTP client primitives")
            _warned_missing_aiohttp = True
        return False
    return requested


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

class REQUEST(object):
    """
    This is a parent class for generating http requests that follow the 
    FludProtocol.
    """
    def __init__(self, host, port, node=None):
        """
        All children should inherit.  By convention, subclasses should 
        create a URL and attempt to retrieve it in the constructor.
        @param node the requestor's node object
        """
        self.host = host
        self.port = port
        self.dest = "%s:%d" % (host, port)
        if node:
            self.node = node
            self.config = node.config
        self.headers = {'Fludprotocol': PROTOCOL_VERSION,
                'User-Agent': 'FludClient'}

    def _run_async_request(self, coro):
        return self.node.async_runtime.deferred_from_coro(coro)

    async def _request(self, method, url, **kwargs):
        return await self.node.async_http.request(method, url, **kwargs)


class SENDGETID(REQUEST):

    def __init__(self, node, host, port):
        """
        Send a request to retrive the node's ID.  This is a reciprocal
        request -- must send my own ID in order to get one back.
        """
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)
        Ku = self.node.config.Ku.exportPublicKey()
        url = "http://"+host+":"+str(port)+"/ID?"
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        #self.nKu = {}
        self.timeoutcount = 0
        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, node, host, port, url))

    def startRequest(self, node, host, port, url):
        loggerid.info("sending SENDGETID to %s" % self.dest)
        d = self._sendRequest(node, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)
        d.addErrback(self._errID, node, host, port, url)

    def _sendRequest(self, node, host, port, url):
        factory = getPageFactory(url, timeout=primitive_to,
                headers=self.headers)
        d2 = factory.deferred
        d2.addCallback(self._getID, factory, host, port)
        d2.addErrback(self._errID, node, host, port, url)
        return d2
        
    def _getID(self, response, factory, host, port):
        loggerid.debug( "received ID response: %s" % response)
        if not hasattr(factory, 'status'):
            raise failure.DefaultException(
                    "SENDGETID FAILED: no status in factory")
        if eval(factory.status) != twebhttp.OK:
            raise failure.DefaultException("SENDGETID FAILED to "+self.dest+": "
                    +"server sent status "+factory.status+", '"+response+"'")
        try:
            nKu = {}
            nKu = eval(response)
            nKu = FludRSA.importPublicKey(nKu)
            loggerid.info("SENDGETID PASSED to %s" % self.dest)
            updateNode(self.node.client, self.config, host, port, nKu)
            return nKu
        except:
            raise failure.DefaultException("SENDGETID FAILED to "+self.dest+": "
                    +"received response, but it did not contain valid key")

    def _errID(self, err, node, host, port, url):
        if err.check('twisted.internet.error.TimeoutError') or \
                err.check('twisted.internet.error.ConnectionLost'):
            #print "GETID request error: %s" % err.__class__.__name__
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                #print "trying again [#%d]...." % self.timeoutcount
                return self._sendRequest(node, host, port, url) 
            else:
                #print "not trying again [#%d]" % self.timeoutcount
                return err
        # XXX: updateNode
        #print "_errID: %s" % err
        #print "_errID: %s" % str(err.stack)
        return err


class SENDGETID_ASYNC(REQUEST):

    def __init__(self, node, host, port):
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)
        Ku = self.node.config.Ku.exportPublicKey()
        url = "http://"+host+":"+str(port)+"/ID?"
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        self.timeoutcount = 0
        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, node, host, port, url))

    def startRequest(self, node, host, port, url):
        loggerid.info("sending SENDGETID to %s (async)" % self.dest)
        d = self._sendRequest(node, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)
        d.addErrback(self._errID, node, host, port, url)

    def _sendRequest(self, node, host, port, url):
        deferred = self._run_async_request(
                self._async_request(node, host, port, url))
        deferred.addErrback(self._errID, node, host, port, url)
        return deferred

    async def _async_request(self, node, host, port, url):
        if aiohttp is None:
            raise failure.DefaultException("aiohttp not available for async ID")
        try:
            timeout = aiohttp.ClientTimeout(total=primitive_to)
            resp = await self._request(
                    "GET", url,
                    headers=_normalize_headers(self.headers),
                    timeout=timeout)
            try:
                status = resp.status
                body = await resp.text()
            finally:
                resp.release()
            if status != twebhttp.OK:
                raise failure.DefaultException(
                        "SENDGETID FAILED to %s: server sent status %s, '%s'"
                        % (self.dest, status, body))
            try:
                nKu = FludRSA.importPublicKey(eval(body))
            except Exception:
                raise failure.DefaultException(
                        "SENDGETID FAILED to %s: received response, but it"
                        " did not contain valid key" % self.dest)
            loggerid.info("SENDGETID PASSED to %s" % self.dest)
            updateNode(self.node.client, self.config, host, port, nKu)
            return nKu
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))

    def _errID(self, err, node, host, port, url):
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                return self._sendRequest(node, host, port, url)
            return err
        return err


# XXX: either 1) produce filekey here or 2) send it in as part of API
#      (similar fixes for SENDRETRIEVE and VERIFY)?  Currently filekey is
#      chosen by caller, and is simply the filename.
class SENDSTORE(REQUEST):

    def __init__(self, nKu, node, host, port, datafile, metadata=None, fsize=0):
        """
        Try to upload a file.
        """
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        loggerstor.info("sending STORE request to %s" % self.dest)
        if not fsize:
            fsize = os.stat(datafile)[stat.ST_SIZE]
        Ku = self.node.config.Ku.exportPublicKey()
        filekey = os.path.basename(datafile) # check this before sending
        params = [('nodeID', self.node.config.nodeID),
                ('Ku_e', str(Ku['e'])),
                ('Ku_n', str(Ku['n'])),
                ('port', str(self.node.config.port)),
                ('size', str(fsize))]
        self.timeoutcount = 0

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, 
                filekey, datafile, metadata, params, True))
        #self.deferred = self._sendRequest(self.headers, nKu, host, port,
        #       datafile, params, True)

    def startRequest(self, headers, nKu, host, port, filekey, 
            datafile, metadata, params, skipFile):
        d = self._sendRequest(headers, nKu, host, port, filekey,
                datafile, metadata, params, skipFile)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, filekey, 
            datafile, metadata, params, skipfile=False):
        """
        skipfile - set to True if you want to send everything but file data
        (used to send the unauthorized request before responding to challenge)
        """
        if skipfile:
            files = [(None, 'filename')]
        elif metadata:
            metakey = metadata[0]
            params.append(('metakey', metakey))
            metafile = metadata[1]
            files = [(datafile, 'filename'), (metafile, 'meta')]
        else:
            files = [(datafile, 'filename')]
        deferred = threads.deferToThread(fileUpload, host, port, 
                '/file/%s' % filekey, files, params, headers=self.headers)
        deferred.addCallback(self._getSendStore, nKu, host, port, filekey,
                datafile, metadata, params, self.headers)
        deferred.addErrback(self._errSendStore, 
                "Couldn't upload file %s to %s:%d" % (datafile, host, port),
                self.headers, nKu, host, port, filekey, datafile, metadata,
                params)
        return deferred

    def _getSendStore(self, httpconn, nKu, host, port, filekey,
            datafile, metadata, params, headers):
        """
        Check the response for status. 
        """
        deferred2 = threads.deferToThread(httpconn.getresponse)
        deferred2.addCallback(self._getSendStore2, httpconn, nKu, host, port, 
                filekey, datafile, metadata, params, headers)
        deferred2.addErrback(self._errSendStore, "Couldn't get response", 
                headers, nKu, host, port, filekey, datafile, metadata,
                params, httpconn)
        return deferred2

    def _getSendStore2(self, response, httpconn, nKu, host, port,
            filekey, datafile, metadata, params, headers):
        httpconn.close()
        if response.status == twebhttp.UNAUTHORIZED:
            loggerstor.info("SENDSTORE unauthorized, sending credentials")
            challenge = response.reason
            if isinstance(challenge, bytes):
                challenge = challenge.decode("utf-8")
            d = answerChallengeDeferred(challenge, self.node.config.Kr,
                    self.node.config.groupIDu, nKu.id(), headers)
            d.addCallback(self._sendRequest, nKu, host, port, filekey,
                    datafile, metadata, params)
            d.addErrback(self._errSendStore, "Couldn't answerChallenge", 
                    headers, nKu, host, port, filekey, datafile, metadata,
                    params, httpconn)
            return d
        elif response.status == twebhttp.CONFLICT:
            result = response.read()
            # XXX: client should check key before ever sending request
            raise BadCASKeyException("%s %s" 
                    % (response.status, response.reason))
        elif response.status != twebhttp.OK:
            result = response.read()
            raise failure.DefaultException( 
                    "received %s in SENDSTORE response: %s"
                    % (response.status, result))
        else:
            result = response.read()
            updateNode(self.node.client, self.config, host, port, nKu)
            loggerstor.info("received SENDSTORE response from %s: %s" 
                    % (self.dest, str(result)))
            return result

    def _errSendStore(self, err, msg, headers, nKu, host, port,
            filekey, datafile, metadata, params, httpconn=None):
        try:
            if hasattr(err, "getTraceback"):
                loggerstor.warn("SENDSTORE error: %s", err.getTraceback())
            else:
                loggerstor.warn("SENDSTORE error: %s", err)
        except Exception:
            pass
        if err.check('socket.error'):
            #print "SENDSTORE request error: %s" % err.__class__.__name__
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                print("trying again [#%d]...." % self.timeoutcount)
                return self._sendRequest(headers, nKu, host, port, filekey,
                        datafile, metadata, params)
            else:
                print("Maxtimeouts exceeded: %d" % self.timeoutcount)
        elif err.check(BadCASKeyException):
            pass
        else:
            print("%s: unexpected error in SENDSTORE: %s" % (msg, 
                    str(err.getErrorMessage())))
        # XXX: updateNode
        if httpconn:
            httpconn.close()
        #loggerstor.info(msg+": "+err.getErrorMessage())
        return err


class SENDSTORE_ASYNC(REQUEST):

    def __init__(self, nKu, node, host, port, datafile, metadata=None, fsize=0):
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        loggerstor.info("sending STORE request to %s (async)" % self.dest)
        if not fsize:
            fsize = os.stat(datafile)[stat.ST_SIZE]
        Ku = self.node.config.Ku.exportPublicKey()
        filekey = os.path.basename(datafile)
        params = [('nodeID', self.node.config.nodeID),
                ('Ku_e', str(Ku['e'])),
                ('Ku_n', str(Ku['n'])),
                ('port', str(self.node.config.port)),
                ('size', str(fsize))]
        self.timeoutcount = 0

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port,
                filekey, datafile, metadata, params, True))

    def startRequest(self, headers, nKu, host, port, filekey,
            datafile, metadata, params, skipFile):
        d = self._sendRequest(headers, nKu, host, port, filekey,
                datafile, metadata, params, skipFile)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, filekey,
            datafile, metadata, params, skipfile=False):
        if aiohttp is None:
            return defer.fail(failure.DefaultException(
                "aiohttp not available for async STORE"))
        deferred = self._run_async_request(
                self._async_request(headers, nKu, host, port, filekey,
                datafile, metadata, params, skipfile))
        deferred.addErrback(self._errSendStore,
                "Couldn't upload file %s to %s:%d" % (datafile, host, port),
                headers, nKu, host, port, filekey, datafile, metadata, params,
                skipfile)
        return deferred

    async def _async_request(self, headers, nKu, host, port, filekey,
            datafile, metadata, params, skipfile):
        async def _do_request(hdrs, skip):
            url = "http://%s:%d/file/%s" % (host, port, filekey)
            if _async_diag_enabled():
                loggerstor.warning("SENDSTORE async POST %s skip=%s", url, skip)
            norm_headers = {}
            for k, v in hdrs.items():
                if isinstance(v, bytes):
                    v = v.decode("ascii", errors="strict")
                norm_headers[k] = v
            data = aiohttp.FormData()

            params_local = list(params)
            files = []
            if skip:
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

            for file, element in files:
                if file is None:
                    data.add_field(element, b"", filename="null",
                            content_type="application/octet-stream")
                    continue
                if hasattr(file, "read"):
                    file.seek(0, 2)
                    file.seek(0, 0)
                    file_bytes = file.read()
                    if isinstance(file_bytes, str):
                        file_bytes = file_bytes.encode("utf-8")
                    data.add_field(element, file_bytes, filename=element,
                            content_type="application/octet-stream")
                    continue
                with open(file, "rb") as fhandle:
                    file_bytes = fhandle.read()
                data.add_field(element, file_bytes,
                        filename=os.path.basename(file),
                        content_type="application/octet-stream")
            timeout = aiohttp.ClientTimeout(total=primitive_to)
            resp = await self._request("POST", url, data=data,
                    headers=norm_headers, timeout=timeout)
            try:
                status = resp.status
                reason = resp.reason
                body = await resp.read()
            finally:
                resp.release()
            return status, reason, body

        async def _run():
            auth_retries = 0
            hdrs = dict(headers)
            skip = skipfile
            url = "http://%s:%d/file/%s" % (host, port, filekey)
            while True:
                status, reason, body = await _do_request(hdrs, skip)
                if _async_diag_enabled():
                    loggerstor.warning("SENDSTORE async response %s %s %s",
                            status, reason, url)
                if status == twebhttp.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise failure.DefaultException(
                            "SENDSTORE unauthorized (retries exhausted)")
                    challenge = None
                    if body:
                        try:
                            challenge = body.decode("utf-8", errors="ignore")
                        except Exception:
                            challenge = None
                    if not challenge:
                        challenge = reason
                    if _async_diag_enabled():
                        loggerstor.warning("SENDSTORE async retry auth %s", url)
                    hdrs = answerChallenge(challenge, self.node.config.Kr,
                            self.node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    skip = False
                    continue
                if status == twebhttp.CONFLICT:
                    raise BadCASKeyException("%s %s" % (status, reason))
                if status != twebhttp.OK:
                    raise failure.DefaultException(
                        "received %s in SENDSTORE response: %s"
                        % (status, body))
                updateNode(self.node.client, self.config, host, port, nKu)
                loggerstor.info("received SENDSTORE response from %s: %s"
                        % (self.dest, str(body)))
                return body

        try:
            return await _run()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            loggerstor.warn("SENDSTORE async client error: %s", str(exc))
            raise socket.error(str(exc))
        except Exception as exc:
            import traceback
            loggerstor.warn("SENDSTORE async unexpected error: %s",
                    traceback.format_exc())
            loggerstor.warn("SENDSTORE async unexpected error: %s", str(exc))
            raise

    def _errSendStore(self, err, msg, headers, nKu, host, port,
            filekey, datafile, metadata, params, skipfile=False):
        try:
            if hasattr(err, "getTraceback"):
                loggerstor.warn("SENDSTORE async error: %s", err.getTraceback())
            else:
                loggerstor.warn("SENDSTORE async error: %s", str(err))
        except Exception:
            pass
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                loggerstor.info("retrying async SENDSTORE [#%d] to %s:%d",
                        self.timeoutcount, host, port)
                return self._sendRequest(headers, nKu, host, port, filekey,
                        datafile, metadata, params, skipfile)
            loggerstor.warn("async SENDSTORE max timeouts exceeded: %d",
                    self.timeoutcount)
            return err
        if err.check(BadCASKeyException):
            return err
        loggerstor.warn("%s: unexpected error in async SENDSTORE: %s",
                msg, str(err))
        return err


aggDeferredMap = {}  # a map of maps, containing a list of deferreds.  The 
                     # deferred(s) for file 'x' in tarball 'y' are accessed as
                     # aggDeferredMap['y']['x']
aggTimeoutMap = {}   # a map of timout calls for a tarball.  The timeout for
                     # tarball 'y' is stored in aggTimeoutMap['y']
aggStateLock = threading.Lock()
class AggregateStore:

    # XXX: if multiple guys store the same file, we're going to get into bad
    # cb state (the except clause in errbackTarfiles).  Need to catch this
    # as it happens... (this happens e.g. for small files with the same
    # filehash, e.g, 0-byte files, file copies etc).  Should fix this in
    # FludClient -- non-agg store has a similar problem (encoded file chunks
    # get deleted out from under successive STOR ops for the same chunk, i.e.
    # from two concurrent STORs of the same file contents)
    def __init__(self, nKu, node, host, port, datafile, metadata):
        tarfilename = os.path.join(node.config.clientdir,nKu.id())\
                +'-'+host+'-'+str(port)+".tar"
        loggerstoragg.debug("tarfile name is %s" % tarfilename)
        with aggStateLock:
            create_tar = not os.path.exists(tarfilename) \
                    or tarfilename not in aggDeferredMap
            if create_tar:
                loggerstoragg.debug("creating tarfile %s to append %s"
                        % (tarfilename, datafile))
                tar = tarfile.open(tarfilename, "w")
                aggDeferredMap[tarfilename] = {}
            else:
                loggerstoragg.debug("opening tarfile %s to append %s"
                        % (tarfilename, datafile))
                tar = tarfile.open(tarfilename, "a")
        
        if os.path.basename(datafile) not in tar.getnames():
            loggerstoragg.info("adding datafile %s to tarball, %s" 
                    % (os.path.basename(datafile), tar.getnames()))
            loggerstoragg.debug("adding data to tarball")
            tar.add(datafile, os.path.basename(datafile))
        else:
            loggerstoragg.info("skip adding datafile %s to tarball" % datafile)

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

        tar.close()
        loggerstoragg.debug("prepping deferred")
        # XXX: (re)set timeout for tarfilename
        self.deferred = defer.Deferred()
        loggerstoragg.debug("adding deferred on %s for %s" 
                % (tarfilename, datafile))
        with aggStateLock:
            try:
                aggDeferredMap[tarfilename][os.path.basename(datafile)].append(
                        self.deferred)
            except KeyError:
                aggDeferredMap[tarfilename][os.path.basename(datafile)] \
                        = [self.deferred]
        self.resetTimeout(tarfilename, nKu, node, host, port)

    def resetTimeout(self, tarball, nKu, node, host, port):
        loggerstoragg.debug("in resetTimeout...")
        if _use_async_http():
            self._resetAsyncTimeout(tarball, nKu, node, host, port)
            return
        with aggStateLock:
            timeoutFunc = aggTimeoutMap.get(tarball)
            if timeoutFunc is None:
                timeoutFunc = reactor.callLater(
                        TARFILE_TO, self.sendTar, tarball, nKu, node, host, port)
                aggTimeoutMap[tarball] = timeoutFunc
        if timeoutFunc.active() and os.stat(tarball)[stat.ST_SIZE] < MINSTORSIZE:
            loggerstoragg.debug("...reset")
            timeoutFunc.reset(TARFILE_TO)
            return
        loggerstoragg.debug("...didn't reset")

    def _resetAsyncTimeout(self, tarball, nKu, node, host, port):
        runtime = node.async_runtime
        if not os.path.exists(tarball):
            return

        def _schedule():
            handle = aggTimeoutMap.get(tarball)
            if handle is not None:
                handle.cancel()
            size_ok = os.path.exists(tarball) and \
                    os.stat(tarball)[stat.ST_SIZE] < MINSTORSIZE
            if not size_ok:
                return
            aggTimeoutMap[tarball] = runtime.loop.call_later(
                    TARFILE_TO,
                    lambda: runtime.submit(
                        self._sendTarAsync(tarball, nKu, node, host, port)))

        runtime.loop.call_soon_threadsafe(_schedule)

    def _prepareTarball(self, tarball):
        gtarball = tarball+".gz"
        gtar = gzip.GzipFile(gtarball, 'wb')
        try:
            with open(tarball, 'rb') as src:
                gtar.write(src.read())
        finally:
            gtar.close()
        os.remove(tarball)
        return gtarball
        
    def sendTar(self, tarball, nKu, node, host, port):
        gtarball = tarball+".gz"
        loggerstoragg.info(
                "aggregation op triggered, sending tarfile %s to %s:%d" 
                % (gtarball, host, port))
        # XXX: bad blocking io
        gtar = gzip.GzipFile(gtarball, 'wb')
        with open(tarball, 'rb') as src:
            gtar.write(src.read())
        gtar.close()
        os.remove(tarball)
        sender = SENDSTORE_ASYNC if _use_async_http() else SENDSTORE
        self.deferred = sender(nKu, node, host, port, gtarball).deferred
        self.deferred.addCallback(self.callbackTarfiles, tarball)
        self.deferred.addErrback(self.errbackTarfiles, tarball)

    async def _sendTarAsync(self, tarball, nKu, node, host, port):
        loggerstoragg.info(
                "aggregation op triggered, sending tarfile %s.gz to %s:%d (async)"
                % (tarball, host, port))
        try:
            gtarball = await asyncio.to_thread(self._prepareTarball, tarball)
            result = await maybe_await(
                    SENDSTORE_ASYNC(nKu, node, host, port, gtarball).deferred)
        except Exception as exc:
            self.errbackTarfiles(exc, tarball)
            return None
        self.callbackTarfiles(result, tarball)
        return result

    # XXX: make aggDeferredMap use a non-.tar key, so that we don't have to
    # keep passing 'tarball' around (since we removed it and are really only
    # interested in gtarball now, use gtarball at the least)
    def callbackTarfiles(self, result, tarball):
        loggerstoragg.debug("callbackTarfiles")
        gtarball = tarball+".gz"
        tar = tarfile.open(gtarball, "r:gz")
        cbs = []
        try: 
            for tarinfo in tar:
                if tarinfo.name[-5:] != '.meta':
                    dlist = aggDeferredMap[tarball].pop(tarinfo.name) 
                    loggerstoragg.debug("callingback for %s in %s"
                            " (%d deferreds)" 
                            % (tarinfo.name, tarball, len(dlist)))
                    for d in dlist:
                        cbs.append(d)
        except KeyError:
            loggerstoragg.warn("aggDeferredMap has keys: %s" 
                    % str(list(aggDeferredMap.keys())))
            loggerstoragg.warn("aggDeferredMap[%s] has keys: %s" % (tarball, 
                    str(list(aggDeferredMap[tarball].keys()))))
        tar.close()
        with aggStateLock:
            aggDeferredMap.pop(tarball, None)
            handle = aggTimeoutMap.pop(tarball, None)
        if handle is not None and hasattr(handle, "cancel"):
            try:
                handle.cancel()
            except Exception:
                pass
        loggerstoragg.debug("deleting tarball %s" % gtarball)
        os.remove(gtarball)
        for cb in cbs:
            cb.callback(result)

    def errbackTarfiles(self, failure, tarball):
        loggerstoragg.debug("errbackTarfiles")
        gtarball = tarball+".gz"
        tar = tarfile.open(gtarball, "r:gz")
        cbs = []
        try: 
            for tarinfo in tar:
                dlist = aggDeferredMap[tarball].pop(tarinfo.name) 
                loggerstoragg.debug("erringback for %s in %s" 
                        " (%d deferreds)"
                        % (tarinfo.name, tarball, len(dlist)))
                for d in dlist:
                    cbs.append(d)
        except KeyError:
            loggerstoragg.warn("aggDeferredMap has keys: %s" 
                    % str(list(aggDeferredMap.keys())))
            loggerstoragg.warn("aggDeferredMap[%s] has keys: %s" % (tarball, 
                    str(list(aggDeferredMap[tarball].keys()))))
        tar.close()
        with aggStateLock:
            aggDeferredMap.pop(tarball, None)
            handle = aggTimeoutMap.pop(tarball, None)
        if handle is not None and hasattr(handle, "cancel"):
            try:
                handle.cancel()
            except Exception:
                pass
        loggerstoragg.debug("NOT deleting tarball %s (for debug)" % gtarball)
        #os.remove(gtarball)
        for cb in cbs:
            cb.errback(failure)

class SENDRETRIEVE(REQUEST):

    def __init__(self, nKu, node, host, port, filekey, metakey=True):
        """
        Try to download a file.
        """
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        loggerrtrv.info("sending RETRIEVE request to %s:%s" % (host, str(port)))
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/file/'+filekey+'?'
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += "&metakey="+str(metakey)
        #filename = self.node.config.clientdir+'/'+filekey
        self.timeoutcount = 0

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

    def startRequest(self, headers, nKu, host, port, url):
        #print "doing RET: %s" % filename
        loggerrtrv.info("startRequest to %s:%s" % (host, str(port)))
        d = self._sendRequest(headers, nKu, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, url):
        loggerrtrv.info("_sendRequest to %s:%s" % (host, str(port)))
        factory = multipartDownloadPageFactory(url, self.node.config.clientdir,
                headers=headers, timeout=transfer_to)
        deferred = factory.deferred
        deferred.addCallback(self._getSendRetrieve, nKu, host, port, factory)
        deferred.addErrback(self._errSendRetrieve, nKu, host, port, factory, 
                url, headers)
        return deferred

    def _getSendRetrieve(self, response, nKu, host, port, factory):
        loggerrtrv.info("_getSendRetrieve to %s:%s" % (host, str(port)))
        if eval(factory.status) == twebhttp.OK:
            # response is None, since it went to file (if a server error
            # occured, it may be printed in this file)
            # XXX: need to check that file hashes to key! If we don't do this,
            #      malicious nodes can corrupt entire files without detection!
            #result = "received SENDRETRIEVE response"
            loggerrtrv.info("_getSendRetrieve OK from %s:%s" 
                    % (host, str(port)))
            loggerrtrv.info(response)
            updateNode(self.node.client, self.config, host, port, nKu)
            return response
        else:
            loggerrtrv.info("_getSendRetrieve fail from %s:%s" 
                    % (host, str(port)))
            raise failure.DefaultException("SENDRETRIEVE FAILED: "
                    +"server sent status "+factory.status+", '"+str(response)+"'")

    def _errSendRetrieve(self, err, nKu, host, port, factory, url, headers):
        loggerrtrv.info("_errSendRetrieve from %s:%s" % (host, str(port)))
        if err.check('twisted.internet.error.TimeoutError') or \
                err.check('twisted.internet.error.ConnectionLost'): #or \
                #err.check('twisted.internet.error.ConnectBindError'):
            loggerrtrv.info("_errSendRetrieve timeout/connlost from %s:%s" 
                    % (host, str(port)))
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                #print "RETR trying again [#%d]..." % self.timeoutcount
                return self._sendRequest(headers, nKu, host, port, url)
            else:
                #print "RETR timeout exceeded: %d" % self.timeoutcount
                pass
        elif hasattr(factory, 'status') and \
                eval(factory.status) == twebhttp.UNAUTHORIZED:
            loggerrtrv.info("SENDRETRIEVE unauthorized, sending credentials")
            challenge = getattr(factory, "reason", "") or ""
            if isinstance(challenge, bytes):
                challenge = challenge.decode("utf-8")
            d = answerChallengeDeferred(challenge, self.node.config.Kr,
                    self.node.config.groupIDu, nKu.id(), headers)
            d.addCallback(self._sendRequest, nKu, host, port, url)
            #d.addErrback(self._errSendRetrieve, nKu, host, port, factory,
            #       url, headers)
            return d
            #extraheaders = answerChallenge(challenge, self.node.config.Kr,
            #       self.node.config.groupIDu, nKu.id(), self.headers)
            #return self._sendRequest(nKu, host, port, url, extraheaders)
        # XXX: these remaining else clauses are really just for debugging...
        elif hasattr(factory, 'status'):
            if eval(factory.status) == twebhttp.NOT_FOUND:
                err = NotFoundException(err)
            elif eval(factory.status) == twebhttp.BAD_REQUEST:
                err = BadRequestException(err)
        elif err.check('twisted.internet.error.ConnectionRefusedError'):
            pass # fall through to return err
        else:
            print("non-timeout, non-UNAUTH RETR request error: %s" % err)
        # XXX: updateNode
        loggerrtrv.info("SENDRETRIEVE failed")
        raise err

class SENDRETRIEVE_ASYNC(REQUEST):

    def __init__(self, nKu, node, host, port, filekey, metakey=True):
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        loggerrtrv.info("sending RETRIEVE request to %s:%s (async)"
                % (host, str(port)))
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/file/'+filekey+'?'
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += "&metakey="+str(metakey)
        self.timeoutcount = 0

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url,
                filekey))

    def startRequest(self, headers, nKu, host, port, url, filekey):
        d = self._sendRequest(headers, nKu, host, port, url, filekey)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, url, filekey):
        deferred = self._run_async_request(
                self._async_request(headers, nKu, host, port, url, filekey))
        deferred.addErrback(self._errSendRetrieve, nKu, host, port, url,
                headers, filekey)
        return deferred

    async def _async_request(self, headers, nKu, host, port, url, filekey):
        if aiohttp is None:
            raise failure.DefaultException(
                    "aiohttp not available for async RETRIEVE")
        try:
            auth_retries = 0
            hdrs = dict(headers)
            timeout = aiohttp.ClientTimeout(total=transfer_to)
            while True:
                resp = await self._request(
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
                if status == twebhttp.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise failure.DefaultException(
                                "SENDRETRIEVE unauthorized (retries exhausted)")
                    challenge = body.decode("utf-8", errors="ignore") \
                            if body else ""
                    if not challenge:
                        challenge = reason
                    hdrs = answerChallenge(challenge, self.node.config.Kr,
                            self.node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == twebhttp.NOT_FOUND:
                    raise NotFoundException("Not found: %s" % filekey)
                if status == twebhttp.BAD_REQUEST:
                    raise BadRequestException("Bad request for %s" % filekey)
                if status != twebhttp.OK:
                    raise failure.DefaultException(
                            "SENDRETRIEVE FAILED: server sent status %s, '%s'"
                            % (status, body))
                saved = _save_retrieve_response(body, content_type,
                        self.node.config.clientdir, filekey, boundary)
                updateNode(self.node.client, self.config, host, port, nKu)
                return saved
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))

    def _errSendRetrieve(self, err, nKu, host, port, url, headers, filekey):
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                return self._sendRequest(headers, nKu, host, port, url, filekey)
        raise err


class SENDDELETE(REQUEST):

    def __init__(self, nKu, node, host, port, filekey, metakey):
        """
        Try to delete a file.
        """
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        loggerdele.info("sending DELETE request to %s:%s" % (host, str(port)))
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/file/'+filekey+'?'
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += "&metakey="+str(metakey)
        self.timeoutcount = 0
        self.authRetry = 0

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

    def startRequest(self, headers, nKu, host, port, url):
        d = self._sendRequest(headers, nKu, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, url):
        factory = getPageFactory(url, method="DELETE", headers=headers,
                timeout=primitive_to)
        deferred = factory.deferred
        deferred.addCallback(self._getSendDelete, nKu, host, port, factory)
        deferred.addErrback(self._errSendDelete, nKu, host, port, factory, url,
                headers)
        return deferred

    def _getSendDelete(self, response, nKu, host, port, factory):
        if eval(factory.status) == twebhttp.OK:
            loggerdele.info("received SENDDELETE response")
            updateNode(self.node.client, self.config, host, port, nKu)
            return response
        else:
            # XXX: updateNode
            raise failure.DefaultException("SENDDELETE FAILED: "
                    +"server sent status "+factory.status+", '"+response+"'")

    def _errSendDelete(self, err, nKu, host, port, factory, url, headers):
        if err.check('twisted.internet.error.TimeoutError') or \
                err.check('twisted.internet.error.ConnectionLost'):
            #print "DELETE request error: %s" % err.__class__.__name__
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                #print "trying again [#%d]...." % self.timeoutcount
                return self._sendRequest(headers, nKu, host, port, url) 
        elif hasattr(factory, 'status') and \
                eval(factory.status) == twebhttp.UNAUTHORIZED and \
                self.authRetry < MAXAUTHRETRY:
            # XXX: add this authRetry stuff to all the other op classes (so
            # that we don't DOS ourselves and another node
            self.authRetry += 1
            loggerdele.info("SENDDELETE unauthorized, sending credentials")
            challenge = getattr(factory, "reason", "") or ""
            if isinstance(challenge, bytes):
                challenge = challenge.decode("utf-8")
            d = answerChallengeDeferred(challenge, self.node.config.Kr,
                    self.node.config.groupIDu, nKu.id(), headers)
            d.addCallback(self._sendRequest, nKu, host, port, url)
            d.addErrback(self._errSendDelete, nKu, host, port, factory,
                    url, headers)
            return d
        elif hasattr(factory, 'status'):
            # XXX: updateNode
            loggerdele.info("SENDDELETE failed")
            if eval(factory.status) == twebhttp.NOT_FOUND:
                err = NotFoundException(err)
            elif eval(factory.status) == twebhttp.BAD_REQUEST:
                err = BadRequestException(err)
            raise err
        return err

class SENDDELETE_ASYNC(REQUEST):

    def __init__(self, nKu, node, host, port, filekey, metakey):
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        loggerdele.info("sending DELETE request to %s:%s (async)"
                % (host, str(port)))
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/file/'+filekey+'?'
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += "&metakey="+str(metakey)
        self.timeoutcount = 0

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

    def startRequest(self, headers, nKu, host, port, url):
        d = self._sendRequest(headers, nKu, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, url):
        deferred = self._run_async_request(
                self._async_request(headers, nKu, host, port, url))
        deferred.addErrback(self._errSendDelete, nKu, host, port, url, headers)
        return deferred

    async def _async_request(self, headers, nKu, host, port, url):
        if aiohttp is None:
            raise failure.DefaultException("aiohttp not available for async DELETE")
        try:
            auth_retries = 0
            hdrs = dict(headers)
            timeout = aiohttp.ClientTimeout(total=primitive_to)
            while True:
                resp = await self._request(
                        "DELETE", url,
                        headers=_normalize_headers(hdrs),
                        timeout=timeout)
                try:
                    status = resp.status
                    reason = resp.reason
                    body = await resp.text()
                finally:
                    resp.release()
                if status == twebhttp.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise failure.DefaultException(
                                "SENDDELETE unauthorized (retries exhausted)")
                    challenge = body or reason
                    hdrs = answerChallenge(challenge, self.node.config.Kr,
                            self.node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == twebhttp.NOT_FOUND:
                    raise NotFoundException(body or "not found")
                if status == twebhttp.BAD_REQUEST:
                    raise BadRequestException(body or "bad request")
                if status != twebhttp.OK:
                    raise failure.DefaultException(
                            "SENDDELETE FAILED: server sent status %s, '%s'"
                            % (status, body))
                updateNode(self.node.client, self.config, host, port, nKu)
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))

    def _errSendDelete(self, err, nKu, host, port, url, headers):
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                return self._sendRequest(headers, nKu, host, port, url)
        return err


class SENDVERIFY(REQUEST):

    def __init__(self, nKu, node, host, port, filename, offset, length, 
            meta=None):
        """
        Try to verify a file.
        If meta is present, it should be a (metakey, filelikeobj) pair.
        """
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        filekey = os.path.basename(filename) # XXX: filekey should be hash
        loggervrfy.info("sending VERIFY request to %s:%s" % (host, str(port)))
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/hash/'+filekey+'?'
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += "&offset="+str(offset)
        url += "&length="+str(length)
        if meta:
            url += "&metakey="+str(meta[0])
            url += "&meta="+fencode(meta[1].read())
        self.timeoutcount = 0

        if not isinstance(nKu, FludRSA):
            raise ValueError("must pass in a FludRSA as nKu to SENDVERIFY")

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

    def startRequest(self, headers, nKu, host, port, url):
        #loggervrfy.debug("*Doing* VERIFY Request %s" % port)
        d = self._sendRequest(headers, nKu, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, url):
        loggervrfy.debug("in VERIFY sendReq %s" % port)
        factory = getPageFactory(url, headers=headers, timeout=primitive_to)
        deferred = factory.deferred
        deferred.addCallback(self._getSendVerify, nKu, host, port, factory)
        deferred.addErrback(self._errSendVerify, nKu, host, port, factory, url,
                headers)
        return deferred

    def _getSendVerify(self, response, nKu, host, port, factory):
        loggervrfy.debug("got vrfy response")
        if eval(factory.status) == twebhttp.OK:
            loggervrfy.info("received SENDVERIFY response")
            updateNode(self.node.client, self.config, host, port, nKu)
            return response
        else:
            # XXX: updateNode
            loggervrfy.debug("received non-OK SENDVERIFY response")
            raise failure.DefaultException("SENDVERIFY FAILED: "
                    +"server sent status "+factory.status+", '"+response+"'")

    def _errSendVerify(self, err, nKu, host, port, factory, url, headers):
        loggervrfy.debug("got vrfy err")
        if err.check('twisted.internet.error.TimeoutError') or \
                err.check('twisted.internet.error.ConnectionLost'):
            #print "VERIFY request error: %s" % err.__class__.__name__
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                #print "trying again [#%d]...." % self.timeoutcount
                return self._sendRequest(headers, nKu, host, port, url) 
        elif hasattr(factory, 'status') and \
                eval(factory.status) == twebhttp.UNAUTHORIZED:
            loggervrfy.info("SENDVERIFY unauthorized, sending credentials")
            challenge = getattr(factory, "reason", "") or ""
            if isinstance(challenge, bytes):
                challenge = challenge.decode("utf-8")
            d = answerChallengeDeferred(challenge, self.node.config.Kr,
                    self.node.config.groupIDu, nKu.id(), headers)
            d.addCallback(self._sendRequest, nKu, host, port, url)
            d.addErrback(self._errVerify, nKu, host, port, factory,
                    url, headers, challenge)
            #d.addErrback(self._errSendVerify, nKu, host, port, factory,
            #       url, headers)
            return d
        elif hasattr(factory, 'status'):
            # XXX: updateNode
            loggervrfy.info("SENDVERIFY failed: %s" % err.getErrorMessage())
            if eval(factory.status) == twebhttp.NOT_FOUND:
                err = NotFoundException(err)
            elif eval(factory.status) == twebhttp.BAD_REQUEST:
                err = BadRequestException(err)
        raise err

    def _errVerify(self, err, nKu, host, port, factory, url, headers,
            challenge):
        # we can get in here after storing the same file as another node when
        # that data is stored in tarballs under its ID.  It was expected that
        # this would be caught up in _getSendVerify... figure out why it isn't.
        loggervrfy.debug("factory status=%s" % factory.status)
        loggervrfy.debug("couldn't answer challenge from %s:%d, WHOOPS: %s" 
                % (host, port, err.getErrorMessage()))
        loggervrfy.debug("challenge was: '%s'" % challenge)
        return err


class SENDVERIFY_ASYNC(REQUEST):

    def __init__(self, nKu, node, host, port, filename, offset, length,
            meta=None):
        host = getCanonicalIP(host)
        REQUEST.__init__(self, host, port, node)

        filekey = os.path.basename(filename)
        loggervrfy.info("sending VERIFY request to %s:%s (async)"
                % (host, str(port)))
        Ku = self.node.config.Ku.exportPublicKey()
        url = 'http://'+host+':'+str(port)+'/hash/'+filekey+'?'
        url += 'nodeID='+str(self.node.config.nodeID)
        url += '&port='+str(self.node.config.port)
        url += "&Ku_e="+str(Ku['e'])
        url += "&Ku_n="+str(Ku['n'])
        url += "&offset="+str(offset)
        url += "&length="+str(length)
        if meta:
            url += "&metakey="+str(meta[0])
            url += "&meta="+fencode(meta[1].read())
        self.timeoutcount = 0

        if not isinstance(nKu, FludRSA):
            raise ValueError("must pass in a FludRSA as nKu to SENDVERIFY")

        self.deferred = defer.Deferred()
        ConnectionQueue.enqueue((self, self.headers, nKu, host, port, url))

    def startRequest(self, headers, nKu, host, port, url):
        d = self._sendRequest(headers, nKu, host, port, url)
        d.addBoth(ConnectionQueue.checkWaiting)
        d.addCallback(self.deferred.callback)
        d.addErrback(self.deferred.errback)

    def _sendRequest(self, headers, nKu, host, port, url):
        deferred = self._run_async_request(
                self._async_request(headers, nKu, host, port, url))
        deferred.addErrback(self._errSendVerify, nKu, host, port, url, headers)
        return deferred

    async def _async_request(self, headers, nKu, host, port, url):
        if aiohttp is None:
            raise failure.DefaultException("aiohttp not available for async VERIFY")
        try:
            auth_retries = 0
            hdrs = dict(headers)
            timeout = aiohttp.ClientTimeout(total=primitive_to)
            while True:
                resp = await self._request(
                        "GET", url,
                        headers=_normalize_headers(hdrs),
                        timeout=timeout)
                try:
                    status = resp.status
                    reason = resp.reason
                    body = await resp.text()
                finally:
                    resp.release()
                if status == twebhttp.UNAUTHORIZED:
                    if auth_retries >= MAXAUTHRETRY:
                        raise failure.DefaultException(
                                "SENDVERIFY unauthorized (retries exhausted)")
                    challenge = body or reason
                    hdrs = answerChallenge(challenge, self.node.config.Kr,
                            self.node.config.groupIDu, nKu.id(), hdrs)
                    auth_retries += 1
                    continue
                if status == twebhttp.NOT_FOUND:
                    raise NotFoundException(body or "not found")
                if status == twebhttp.BAD_REQUEST:
                    raise BadRequestException(body or "bad request")
                if status != twebhttp.OK:
                    raise failure.DefaultException(
                            "SENDVERIFY FAILED: server sent status %s, '%s'"
                            % (status, body))
                updateNode(self.node.client, self.config, host, port, nKu)
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise socket.error(str(exc))

    def _errSendVerify(self, err, nKu, host, port, url, headers):
        if err.check(socket.error):
            self.timeoutcount += 1
            if self.timeoutcount < MAXTIMEOUTS:
                return self._sendRequest(headers, nKu, host, port, url)
        raise err


def answerChallengeDeferred(challenge, Kr, groupIDu, sID, headers): 
    return threads.deferToThread(answerChallenge, challenge, Kr, groupIDu, sID,
            headers)

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
