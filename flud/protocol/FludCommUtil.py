"""
FludCommUtil.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

Communications routines used by both client and server code.
"""
from twisted.web.client import Agent, readBody, FileBodyProducer
from twisted.web.http_headers import Headers
from twisted.internet import reactor, defer
from twisted.python import failure
import binascii, http.client, logging, os, stat, socket
import urllib.parse
from io import BytesIO
import inspect

from flud.FludExceptions import FludException
from flud.FludCrypto import FludRSA, generateRandom

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
            d = client.sendGetID(host, port)
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
                d = client.sendGetID(host, port)
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
            s = SENDGETID(replacee[0], replacee[1])
            s.addErrback(replaceNode, config.routing, replacee, node)
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
    # if IP is 'localhost' or '127.0.0.1', use the canonical local hostname.
    # (this is mostly useful when multiple clients run on the same host)
    # XXX: could use gethostbyname to get IP addy instead.
    if IP == '127.0.0.1' or IP == 'localhost':
        return socket.getfqdn()
    else:
        return socket.getfqdn(IP)

class _SimpleFactory:
    def __init__(self, deferred):
        self.deferred = deferred
        self.status = None


def _headers_from_dict(headers):
    if not headers:
        return Headers({})
    normalized = {}
    for key, value in headers.items():
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        normalized[str(key)] = [str(value)]
    return Headers(normalized)


def _decode_body(body):
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return body


def _extract_boundary(headers):
    boundary = None
    raw = headers.getRawHeaders("boundary")
    if raw:
        boundary = raw[0]
    else:
        content_types = headers.getRawHeaders("content-type") or []
        for value in content_types:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            if "boundary=" in value.lower():
                boundary = value.split("boundary=", 1)[1].strip()
                boundary = boundary.strip('"')
                break
    if isinstance(boundary, bytes):
        boundary = boundary.decode("utf-8")
    return boundary


def _parse_multipart(body, boundary):
    if isinstance(boundary, str):
        boundary = boundary.encode("utf-8")
    marker = b"--" + boundary
    parts = []
    index = 0
    while True:
        start = body.find(marker, index)
        if start == -1:
            break
        start += len(marker)
        if body[start:start+2] == b"--":
            break
        if body[start:start+2] == b"\r\n":
            start += 2
        header_end = body.find(b"\r\n\r\n", start)
        if header_end == -1:
            break
        header_blob = body[start:header_end].decode("utf-8", errors="replace")
        headers = {}
        for line in header_blob.split("\r\n"):
            if not line:
                continue
            k, v = line.split(":", 1)
            headers[k.lower()] = v.strip()
        content_start = header_end + 4
        length = int(headers.get("content-length", "0"))
        content = body[content_start:content_start+length]
        parts.append((headers, content))
        index = content_start + length
    return parts


def _save_multipart(body, boundary, target_dir):
    filenames = []
    for headers, content in _parse_multipart(body, boundary):
        content_id = headers.get("content-id")
        if not content_id:
            continue
        filename = os.path.join(target_dir, content_id)
        with open(filename, "wb") as f:
            f.write(content)
        filenames.append(filename)
    return filenames


def getPageFactory(url, contextFactory=None, *args, **kwargs):
    method = kwargs.pop("method", "GET")
    headers = kwargs.pop("headers", {})
    postdata = kwargs.pop("postdata", None)

    if len(url) >= 16384:
        raise ValueError(
                "Too much data sent: twisted server doesn't appear to"
                " support urls longer than 16384")

    bodyProducer = None
    if postdata is not None:
        if isinstance(postdata, str):
            postdata = postdata.encode("utf-8")
        bodyProducer = FileBodyProducer(BytesIO(postdata))

    agent = Agent(reactor, contextFactory)
    d = agent.request(
            method.encode("ascii"),
            url.encode("ascii"),
            _headers_from_dict(headers),
            bodyProducer)
    factory = _SimpleFactory(d)

    def got_response(response):
        factory.status = str(response.code)
        reason = response.phrase
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8", errors="replace")
        factory.reason = reason
        factory.response_headers = {}
        for name in response.headers.getAllRawHeaders():
            key, values = name
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            vals = []
            for v in values:
                if isinstance(v, bytes):
                    v = v.decode("utf-8")
                vals.append(v)
            factory.response_headers[key.lower()] = vals
        dbody = readBody(response)
        dbody.addCallback(_decode_body)
        return dbody

    d.addCallback(got_response)
    return factory

def downloadPageFactory(url, file, contextFactory=None, timeout=None, 
        *args, **kwargs):
    headers = kwargs.pop("headers", {})
    agent = Agent(reactor, contextFactory)
    d = agent.request(
            b"GET",
            url.encode("ascii"),
            _headers_from_dict(headers),
            None)
    factory = _SimpleFactory(d)

    def got_response(response):
        factory.status = str(response.code)
        reason = response.phrase
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8", errors="replace")
        factory.reason = reason
        factory.response_headers = {}
        for name in response.headers.getAllRawHeaders():
            key, values = name
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            vals = []
            for v in values:
                if isinstance(v, bytes):
                    v = v.decode("utf-8")
                vals.append(v)
            factory.response_headers[key.lower()] = vals
        dbody = readBody(response)
        def write_file(body):
            with open(file, "wb") as f:
                f.write(body)
            return file
        dbody.addCallback(write_file)
        return dbody

    d.addCallback(got_response)
    return factory

def multipartDownloadPageFactory(url, dir, contextFactory=None, timeout=None,
        *args, **kwargs):
    headers = kwargs.pop("headers", {})
    agent = Agent(reactor, contextFactory)
    d = agent.request(
            b"GET",
            url.encode("ascii"),
            _headers_from_dict(headers),
            None)
    factory = _SimpleFactory(d)

    def got_response(response):
        factory.status = str(response.code)
        reason = response.phrase
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8", errors="replace")
        factory.reason = reason
        factory.response_headers = {}
        for name in response.headers.getAllRawHeaders():
            key, values = name
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            vals = []
            for v in values:
                if isinstance(v, bytes):
                    v = v.decode("utf-8")
                vals.append(v)
            factory.response_headers[key.lower()] = vals
        dbody = readBody(response)
        def save_body(body):
            boundary = _extract_boundary(response.headers)
            if boundary:
                return _save_multipart(body, boundary, dir)
            parsed = urllib.parse.urlparse(url)
            filekey = os.path.basename(parsed.path)
            filename = os.path.join(dir, filekey)
            with open(filename, "wb") as f:
                f.write(body)
            return [filename]
        dbody.addCallback(save_body)
        return dbody

    d.addCallback(got_response)
    return factory

def fileUpload(host, port, selector, files, form=(), headers={}):
    """
    Performs a file upload via http.
    host - webserver hostname
    port - webserver listen port
    selector - the request (relative URL)
    files - list of files to upload.  list contains tuples, with the first
        entry as filename/file-like obj and the second as form element name.
        If the first element is a file-like obj, the element will be used as
        the filename.  If the first element is a filename, the filename's
        basename will be used as the filename on the form.  Type will be
        "application/octet-stream"
    form (optional) - a list of pairs of additional name/value form elements 
        (param/values).
    [hopefully, this method goes away in twisted-web2]
    """
    # XXX: set timeout (based on filesize?)
    port = int(port)

    rand_bound = binascii.hexlify(generateRandom(13))
    if isinstance(rand_bound, bytes):
        rand_bound = rand_bound.decode("ascii")
    boundary_str = "---------------------------"+rand_bound
    boundary = boundary_str.encode("ascii")
    CRLF = b'\r\n'
    body_content_type = "application/octet-stream"
    content_type = "multipart/form-data; boundary="+boundary_str
    content_length = 0

    H = []
    for (param, value) in form:
        H.append(b'--' + boundary)
        H.append(
                ('Content-Disposition: form-data; name="%s"' % param)
                .encode("utf-8"))
        H.append(b'')
        H.append(('%s' % value).encode("utf-8"))
    form_data = CRLF.join(H)+CRLF
    content_length = content_length + len(form_data)

    fuploads = []
    for file, element in files:
        if file == None:
            file = "/dev/null"   # XXX: not portable 

        if 'read' in dir(file):
            fname = element
            file.seek(0,2)
            file_length = file.tell()
            file.seek(0,0)
            file_bytes = file.read()
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            file_length = len(file_bytes)
        else:
            fname = os.path.basename(file)
            file_length = os.stat(file)[stat.ST_SIZE]
            file_bytes = None

        #logger.info("upload file %s len is %d" % (fname, file_length))

        H = []  # stuff that goes above file data
        T = []  # stuff that goes below file data
        H.append(b'--' + boundary)
        H.append(
                ('Content-Disposition: form-data; name="%s"; filename="%s"' 
                % (element, fname)).encode("utf-8"))
        H.append(('Content-Type: %s' % body_content_type).encode("utf-8"))
        H.append(b'')
        file_headers = CRLF.join(H) + CRLF

        content_length = content_length + len(file_headers) + file_length \
                + len(CRLF)
        fuploads.append((file_headers, file, file_length, file_bytes))

    T.append(b'--'+boundary+b'--')
    T.append(b'')
    T.append(b'')
    trailer = CRLF.join(T)
    content_length = content_length + len(trailer)
        
    h = http.client.HTTPConnection(host, port) # XXX: blocking
    h.putrequest('POST', selector)
    for pageheader in headers:
        h.putheader(pageheader, headers[pageheader])
    h.putheader('Content-Type', content_type)
    h.putheader('Content-Length', content_length)
    h.endheaders()

    h.send(form_data)

    for fheader, file, flen, file_bytes in fuploads:
        h.send(fheader)
        if file_bytes is not None:
            h.send(file_bytes)
        else:
            with open(file, 'rb') as fhandle:
                while True:
                    chunk = fhandle.read(1048576)
                    if not chunk:
                        break
                    h.send(chunk)
        h.send(CRLF) # XXX: blocking

    h.send(trailer)

    return h

class ImposterException(FludException):
    pass
