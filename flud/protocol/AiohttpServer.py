"""
AiohttpServer.py

Asyncio/aiohttp HTTP server for Flud Phase 3 migration.
"""

import asyncio
import base64
import binascii
import logging
import os
import random
import tarfile
import tempfile
import threading
from io import BytesIO

from aiohttp import web

import flud.TarfileUtils as TarfileUtils
from flud.FludCrypto import FludRSA, generateRandom, hashfile, hashstring
from flud.fencode import fencode, fdecode

from . import BlockFile
from .AsyncLocal import AsyncLocalServer
from .FludCommUtil import PROTOCOL_VERSION, primitive_to, requireParams, updateNode, getCanonicalIP

logger = logging.getLogger("flud.server.aiohttp")


class _RequestAdapter:
    def __init__(self, request, extra_args=None):
        self.request = request
        self.args = {}
        for key, value in request.query.items():
            if isinstance(value, str):
                value = value.encode("utf-8")
            self.args[key.encode("utf-8")] = [value]
        if extra_args:
            for key, value in extra_args.items():
                if isinstance(value, str):
                    value = value.encode("utf-8")
                elif isinstance(value, int):
                    value = str(value).encode("utf-8")
                self.args[key.encode("utf-8")] = [value]

    def getClientIP(self):
        host = self.request.remote
        if host:
            return host
        peer = self.request.transport.get_extra_info("peername")
        if isinstance(peer, tuple) and peer:
            return peer[0]
        return "127.0.0.1"


class FludAiohttpServer(threading.Thread):
    def __init__(self, node, port):
        super().__init__()
        self.node = node
        self.port = port
        self.clientport = node.config.clientport
        self._loop = None
        self._runner = None
        self._site = None
        self._stop_event = None
        self._local_server = None
        self._challenges = {}
        self.daemon = True

    def _base_headers(self):
        return {
            "Server": "FludServer 0.1",
            "FludProtocol": PROTOCOL_VERSION,
        }

    def _response(self, status=200, text=None, body=None, headers=None, reason=None):
        hdrs = self._base_headers()
        if headers:
            hdrs.update(headers)
        if body is not None:
            return web.Response(status=status, body=body, headers=hdrs, reason=reason)
        return web.Response(status=status, text=text or "", headers=hdrs, reason=reason)

    def _parse_basic_auth(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return None, None
        token = auth.split(" ", 1)[1].strip()
        try:
            raw = base64.b64decode(token).decode("utf-8", errors="replace")
        except Exception:
            return None, None
        if ":" not in raw:
            return raw, ""
        user, password = raw.split(":", 1)
        return user, password

    def _add_challenge(self, challenge):
        self._challenges[challenge] = asyncio.get_running_loop().time() + (primitive_to * 15)

    def _expire_challenge(self, challenge_response):
        try:
            challenge = fdecode(challenge_response)
        except Exception:
            challenge = challenge_response
        self._challenges.pop(challenge, None)

    def _get_challenge(self, challenge_response):
        try:
            challenge = fdecode(challenge_response)
        except Exception:
            challenge = challenge_response
        expiry = self._challenges.get(challenge)
        if expiry is None:
            return None
        if expiry < asyncio.get_running_loop().time():
            self._challenges.pop(challenge, None)
            return None
        return challenge

    def _send_challenge(self, req_ku, node_id):
        challenge = generateRandom(40)
        while challenge[0] == 0:
            challenge = generateRandom(40)
        self._add_challenge(challenge)
        echallenge = req_ku.encrypt(binascii.unhexlify(node_id) + challenge)[0]
        echallenge = fencode(echallenge)
        body = "challenge = %s" % echallenge
        headers = {
            "Connection": "close",
            "WWW-Authenticate": 'Basic realm="default"',
            "Content-Type": "text/html",
            "Pragma": "claimreserve=5555",
        }
        return self._response(status=401, reason=echallenge, text=body, headers=headers)

    def _authenticate(self, request, req_ku, host, port):
        challenge_response, group_response = self._parse_basic_auth(request)
        if not challenge_response or not group_response:
            return self._send_challenge(req_ku, self.node.config.nodeID)

        if self._get_challenge(challenge_response):
            self._expire_challenge(challenge_response)
            expected_group = hashstring(str(req_ku.exportPublicKey()) + str(self.node.config.groupIDr))
            if group_response == expected_group:
                updateNode(self.node.client, self.node.config, host, port, req_ku, req_ku.id())
                return None
            return self._response(status=403, text="Group Challenge Failed")
        return self._response(status=403, text="Challenge Failed")

    def _field_bytes(self, form, name):
        if name not in form:
            return None
        value = form[name]
        if hasattr(value, "file"):
            data = value.file.read()
            if isinstance(data, str):
                data = data.encode("utf-8")
            return data
        if isinstance(value, bytes):
            return value
        if value is None:
            return None
        return str(value).encode("utf-8")

    def _build_multipart(self, parts, boundary):
        chunks = []
        for content_id, payload in parts:
            chunks.append(("--%s\r\n" % boundary).encode("utf-8"))
            chunks.append(b"Content-Type: Application/octet-stream\r\n")
            chunks.append(("Content-ID: %s\r\n" % content_id).encode("utf-8"))
            chunks.append(("Content-Length: %d\r\n" % len(payload)).encode("utf-8"))
            chunks.append(b"\r\n")
            chunks.append(payload)
            chunks.append(b"\r\n")
        chunks.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
        return b"".join(chunks)

    async def _handle_root(self, request):
        return self._response(text="<html>Flud</html>")

    async def _handle_id(self, request):
        req = _RequestAdapter(request)
        try:
            params = requireParams(req, ("nodeID", "Ku_e", "Ku_n", "port"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by ID" % exc.args[0])

        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        if req_ku.id() != params["nodeID"]:
            return self._response(status=400, text="requesting node's ID and public key do not match")

        host = getCanonicalIP(req.getClientIP())
        updateNode(self.node.client, self.node.config, host, int(params["port"]), req_ku, params["nodeID"])
        return self._response(text=str(self.node.config.Ku.exportPublicKey()))

    async def _handle_file_post(self, request):
        form = await request.post()
        form_args = {}
        for k, v in form.items():
            # Only scalar form fields belong in args for requireParams;
            # file payload fields are handled separately below.
            if hasattr(v, "file"):
                continue
            form_args[k] = v

        req = _RequestAdapter(request, extra_args=form_args)
        filekey = request.match_info["filekey"]
        try:
            params = requireParams(req, ("size", "Ku_e", "Ku_n", "port"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by STORE" % exc.args[0])

        host = getCanonicalIP(req.getClientIP())
        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        auth_resp = self._authenticate(request, req_ku, host, int(params["port"]))
        if auth_resp is not None:
            return auth_resp

        data = self._field_bytes(form, "filename")
        if data is None:
            return self._response(status=400, text="Bad request: missing file payload in STORE")

        tmpfile = tempfile.mktemp(dir=self.node.config.storedir)
        tarball_base = os.path.join(self.node.config.storedir, req_ku.id()) + ".tar"
        tarball = tarball_base

        tmp_tar_mode = None
        if filekey.endswith(".tar"):
            tmpfile = tmpfile + ".tar"
            tmp_tar_mode = "r"
            target_tar = tarball
        elif filekey.endswith(".tar.gz"):
            tmpfile = tmpfile + ".tar.gz"
            tmp_tar_mode = "r:gz"
            target_tar = tarball + ".gz"

        if os.path.exists(tarball + ".gz"):
            tarball = (tarball + ".gz", "r:gz")
        elif os.path.exists(tarball):
            tarball = (tarball, "r")
        else:
            tarball = None

        with open(tmpfile, "wb") as f:
            f.write(data)

        node_id = req_ku.id()
        if tmp_tar_mode:
            if not data:
                return self._response(status=400, text="Bad request: empty tar payload in STORE")
            digests = TarfileUtils.verifyHashes(tmpfile, ".meta")
            if not digests:
                os.remove(tmpfile)
                return self._response(status=409, text="Attempted to use non-CAS storage key(s) for STORE tarball")
            gzipped_target = target_tar.endswith(".gz")
            work_tar = target_tar[:-3] if gzipped_target else target_tar
            if os.path.exists(target_tar) and gzipped_target:
                try:
                    work_tar = TarfileUtils.gunzipTarball(target_tar)
                except Exception as exc:
                    logger.warning("STORE tar merge: failed to gunzip %s: %s",
                            target_tar, str(exc))
                    try:
                        os.remove(target_tar)
                    except Exception:
                        pass
            mode = "a" if os.path.exists(work_tar) else "w"
            try:
                dst = tarfile.open(work_tar, mode)
            except (tarfile.ReadError, EOFError) as exc:
                logger.warning("STORE tar merge: replacing corrupt tarball %s: %s",
                        work_tar, str(exc))
                try:
                    os.remove(work_tar)
                except Exception:
                    pass
                dst = tarfile.open(work_tar, "w")
            try:
                try:
                    existing = set(dst.getnames())
                except (tarfile.ReadError, EOFError):
                    existing = set()
                src = tarfile.open(tmpfile, tmp_tar_mode)
                try:
                    for member in src.getmembers():
                        if member.name in existing:
                            continue
                        fileobj = src.extractfile(member) if member.isfile() else None
                        dst.addfile(member, fileobj)
                        if fileobj:
                            fileobj.close()
                finally:
                    src.close()
            finally:
                dst.close()
            try:
                os.remove(tmpfile)
            except Exception:
                pass
            if gzipped_target:
                TarfileUtils.gzipTarball(work_tar)
            return self._response(text="Successful STORE")

        h = hashfile(tmpfile)
        if fencode(int(h, 16)) != filekey:
            os.remove(tmpfile)
            msg = "Attempted to use non-CAS storage key for STORE data (%s != %s)" % (filekey, fencode(int(h, 16)))
            return self._response(status=409, text=msg)

        metakey = form.get("metakey")
        if metakey is not None:
            metakey = str(metakey)
        meta = self._field_bytes(form, "meta")

        fname = os.path.join(self.node.config.storedir, filekey)
        if os.path.exists(fname):
            f = BlockFile.open(fname, "rb+")
            if not f.hasNode(node_id):
                f.addNode(int(node_id, 16), {metakey: meta})
                f.close()
            else:
                f.close()
            os.remove(tmpfile)
            return self._response(text="Successful STORE")

        tarname = tarball_base
        tarball_paths = []
        if os.path.exists(tarname + ".gz"):
            tarball_paths.append((tarname + ".gz", "r:gz"))
        if os.path.exists(tarname):
            tarball_paths.append((tarname, "r"))

        for tarpath, openmode in tarball_paths:
            try:
                tar = tarfile.open(tarpath, openmode)
            except (tarfile.ReadError, EOFError) as exc:
                logger.warning("STORE metadata check: removing corrupt tarball %s: %s",
                        tarpath, str(exc))
                try:
                    os.remove(tarpath)
                except Exception:
                    pass
                continue
            try:
                names = tar.getnames()
                if filekey in names:
                    if meta and metakey is not None:
                        mfname = "%s.%s.meta" % (filekey, metakey)
                        if mfname not in names:
                            tar.close()
                            if openmode == "r:gz":
                                tarpath = TarfileUtils.gunzipTarball(tarpath)
                            tar = tarfile.open(tarpath, "a")
                            metaio = BytesIO(meta)
                            tinfo = tarfile.TarInfo(mfname)
                            tinfo.size = len(meta)
                            tar.addfile(tinfo, metaio)
                            tar.close()
                            if openmode == "r:gz":
                                TarfileUtils.gzipTarball(tarpath)
                    return self._response(text="Successful STORE")
            except (tarfile.ReadError, EOFError) as exc:
                # Corrupt or partially-written tarball; ignore and continue.
                logger.warning("STORE metadata read: corrupt tarball %s: %s",
                        tarpath, str(exc))
                try:
                    os.remove(tarpath)
                except Exception:
                    pass
                continue
            finally:
                try:
                    tar.close()
                except Exception:
                    pass

        if len(data) < 8192 and fname != tarname:
            gzipped = False
            if os.path.exists(tarname + ".gz"):
                tarname = TarfileUtils.gunzipTarball(tarname + ".gz")
                gzipped = True
            if not os.path.exists(tarname):
                tarballf = tarfile.open(tarname, "w")
            else:
                try:
                    tarballf = tarfile.open(tarname, "a")
                except (tarfile.ReadError, EOFError) as exc:
                    logger.warning("STORE aggregation: replacing corrupt tarball %s: %s",
                            tarname, str(exc))
                    try:
                        os.remove(tarname)
                    except Exception:
                        pass
                    tarballf = tarfile.open(tarname, "w")
            tarballf.add(tmpfile, os.path.basename(fname))
            if meta:
                metafilename = "%s.%s.meta" % (os.path.basename(fname), metakey)
                metaio = BytesIO(meta)
                tinfo = tarfile.TarInfo(metafilename)
                tinfo.size = len(meta)
                tarballf.addfile(tinfo, metaio)
            tarballf.close()
            if gzipped:
                TarfileUtils.gzipTarball(tarname)
            os.remove(tmpfile)
        else:
            os.rename(tmpfile, fname)
            BlockFile.convert(fname, (int(node_id, 16), {metakey: meta}))

        return self._response(text="Successful STORE")

    async def _handle_file_get(self, request):
        req = _RequestAdapter(request)
        filekey = request.match_info["filekey"]
        try:
            params = requireParams(req, ("Ku_e", "Ku_n", "port"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by RETRIEVE" % exc.args[0])

        host = getCanonicalIP(req.getClientIP())
        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        auth_resp = self._authenticate(request, req_ku, host, int(params["port"]))
        if auth_resp is not None:
            return auth_resp

        metakey = request.query.get("metakey")
        if metakey == "True":
            metakey = None
        req_node_id = request.query.get("nodeID")

        fname = os.path.join(self.node.config.storedir, filekey)
        boundary = binascii.hexlify(generateRandom(13)).decode("ascii")

        if not os.path.exists(fname):
            tarball = os.path.join(self.node.config.storedir, req_ku.id() + ".tar")
            tarballs = []
            if os.path.exists(tarball + ".gz"):
                tarballs.append((tarball + ".gz", "r:gz"))
            if os.path.exists(tarball):
                tarballs.append((tarball, "r"))
            for tarpath, openmode in tarballs:
                try:
                    tar = tarfile.open(tarpath, openmode)
                except (tarfile.ReadError, EOFError) as exc:
                    logger.warning("RETRIEVE: ignoring corrupt tarball %s: %s",
                            tarpath, str(exc))
                    continue
                try:
                    try:
                        tinfo = tar.getmember(filekey)
                    except KeyError:
                        names = tar.getnames()
                        alt = None
                        for n in names:
                            if n == filekey or (n.startswith("./") and n[2:] == filekey) or n.endswith(filekey):
                                alt = n
                                break
                        if not alt:
                            continue
                        tinfo = tar.getmember(alt)

                    data = tar.extractfile(tinfo).read()
                    parts = []
                    metas = [n for n in tar.getnames() if n.startswith(filekey) and n.endswith("meta")]
                    if metakey is not None:
                        metas = [n for n in metas if n == ("%s.%s.meta" % (filekey, metakey))]
                    for m in metas:
                        minfo = tar.getmember(m)
                        mpayload = tar.extractfile(minfo).read()
                        parts.append((m, mpayload))
                    if parts:
                        parts.append((filekey, data))
                        body = self._build_multipart(parts, boundary)
                        return self._response(body=body, headers={"Content-type": "Multipart/Related", "boundary": boundary})
                    return self._response(body=data, headers={"Content-Type": "application/octet-stream"})
                except (tarfile.ReadError, EOFError) as exc:
                    # Twisted path ignores corrupt tarballs and continues.
                    logger.warning("RETRIEVE: corrupt tarball while reading %s: %s",
                            tarpath, str(exc))
                    continue
                finally:
                    tar.close()
            return self._response(status=404, text="Not found: %s" % filekey)

        f = BlockFile.open(fname, "rb")
        req_meta_id = req_ku.id()
        if req_node_id:
            req_meta_id = req_node_id
        meta = f.meta(int(req_meta_id, 16))
        if metakey is not None and meta:
            meta = {metakey: meta.get(metakey)} if metakey in meta else None
        payload = f.read()
        f.close()

        parts = []
        if meta:
            meta = {k: (v if isinstance(v, bytes) else str(v).encode("utf-8")) for k, v in meta.items()}
            for m in meta:
                parts.append(("%s.%s.meta" % (filekey, m), meta[m]))
        if parts:
            parts.append((filekey, payload))
            body = self._build_multipart(parts, boundary)
            return self._response(body=body, headers={"Content-type": "Multipart/Related", "boundary": boundary})
        return self._response(body=payload, headers={"Content-Type": "application/octet-stream"})

    async def _handle_hash_get(self, request):
        req = _RequestAdapter(request)
        filekey = request.match_info["filekey"]
        try:
            params = requireParams(req, ("Ku_e", "Ku_n", "port", "offset", "length"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by VERIFY" % exc.args[0])

        host = getCanonicalIP(req.getClientIP())
        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        auth_resp = self._authenticate(request, req_ku, host, int(params["port"]))
        if auth_resp is not None:
            return auth_resp

        offset = int(params["offset"])
        length = int(params["length"])
        paths = [p for p in filekey.split(os.path.sep) if p != ""]
        if len(paths) > 1:
            return self._response(status=400, text="Bad request: filekey contains illegal path seperator tokens.")

        meta = None
        if "meta" in request.query and "metakey" in request.query:
            meta_raw = request.query["meta"]
            meta_dec = fdecode(meta_raw)
            if isinstance(meta_dec, str):
                meta_dec = meta_dec.encode("utf-8")
            meta = (request.query["metakey"], meta_dec)

        fname = os.path.join(self.node.config.storedir, filekey)
        if os.path.exists(fname):
            f = BlockFile.open(fname, "rb+" if meta else "rb")
            fsize = os.stat(fname).st_size
            if offset > fsize or (offset + length) > fsize:
                f.close()
                return self._response(status=400, text="Bad request: bad offset/length in VERIFY")
            f.seek(offset)
            data = f.read(length)
            if meta:
                f.addNode(int(req_ku.id(), 16), {meta[0]: meta[1]})
            f.close()
            return self._response(text=hashstring(data))

        tarballs = []
        tarballbase = os.path.join(self.node.config.storedir, req_ku.id()) + ".tar"
        if os.path.exists(tarballbase + ".gz"):
            tarballs.append((tarballbase + ".gz", "r:gz"))
        if os.path.exists(tarballbase):
            tarballs.append((tarballbase, "r"))

        for tarball, openmode in tarballs:
            try:
                tar = tarfile.open(tarball, openmode)
            except (tarfile.ReadError, EOFError) as exc:
                logger.warning("VERIFY: ignoring corrupt tarball %s: %s",
                        tarball, str(exc))
                continue
            try:
                tarf = tar.extractfile(filekey)
                tari = tar.getmember(filekey)
                fsize = tari.size
                if offset > fsize or (offset + length) > fsize:
                    return self._response(status=400, text="Bad request: bad offset/length in VERIFY")
                tarf.seek(offset)
                data = tarf.read(length)
                tarf.close()

                if meta:
                    mfname = "%s.%s.meta" % (filekey, meta[0])
                    if mfname in tar.getnames():
                        tarmf = tar.extractfile(mfname)
                        stored_meta = tarmf.read()
                        tarmf.close()
                        if meta[1] != stored_meta:
                            tar.close()
                            TarfileUtils.delete(tarball, mfname)
                            if openmode == "r:gz":
                                tarball = TarfileUtils.gunzipTarball(tarball)
                            tar = tarfile.open(tarball, "a")
                            metaio = BytesIO(meta[1])
                            tinfo = tarfile.TarInfo(mfname)
                            tinfo.size = len(meta[1])
                            tar.addfile(tinfo, metaio)
                            tar.close()
                            if openmode == "r:gz":
                                TarfileUtils.gzipTarball(tarball)
                    else:
                        tar.close()
                        if openmode == "r:gz":
                            tarball = TarfileUtils.gunzipTarball(tarball)
                        tar = tarfile.open(tarball, "a")
                        metaio = BytesIO(meta[1])
                        tinfo = tarfile.TarInfo(mfname)
                        tinfo.size = len(meta[1])
                        tar.addfile(tinfo, metaio)
                        tar.close()
                        if openmode == "r:gz":
                            TarfileUtils.gzipTarball(tarball)
                return self._response(text=hashstring(data))
            except Exception:
                pass
            finally:
                try:
                    tar.close()
                except Exception:
                    pass

        return self._response(status=404, text="Not found: not storing %s" % filekey)

    async def _handle_file_delete(self, request):
        req = _RequestAdapter(request)
        filekey = request.match_info["filekey"]
        try:
            params = requireParams(req, ("Ku_e", "Ku_n", "port", "metakey"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by DELETE" % exc.args[0])

        host = getCanonicalIP(req.getClientIP())
        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        auth_resp = self._authenticate(request, req_ku, host, int(params["port"]))
        if auth_resp is not None:
            return auth_resp

        metakey = params["metakey"]
        req_id = req_ku.id()
        fname = os.path.join(self.node.config.storedir, filekey)
        if not os.path.exists(fname):
            tarballs = []
            tarballbase = os.path.join(self.node.config.storedir, req_ku.id()) + ".tar"
            if os.path.exists(tarballbase + ".gz"):
                tarballs.append((tarballbase + ".gz", "r:gz"))
            if os.path.exists(tarballbase):
                tarballs.append((tarballbase, "r"))
            for tarball, openmode in tarballs:
                mfilekey = "%s.%s.meta" % (filekey, metakey)
                try:
                    tar = tarfile.open(tarball, openmode)
                except (tarfile.ReadError, EOFError) as exc:
                    logger.warning("DELETE: ignoring corrupt tarball %s: %s",
                            tarball, str(exc))
                    continue
                mnames = [n for n in tar.getnames() if n[:len(filekey)] == filekey]
                tar.close()
                if len(mnames) > 2:
                    TarfileUtils.delete(tarball, mfilekey)
                else:
                    TarfileUtils.delete(tarball, [filekey, mfilekey])
                return self._response(text="")
            return self._response(status=404, text="Not found: %s" % filekey)

        f = BlockFile.open(fname, "rb+")
        n_id = int(req_id, 16)
        if f.hasNode(n_id):
            f.delNode(n_id, metakey)
            if f.emptyNodes():
                f.close()
                os.remove(fname)
                return self._response(text="")
        f.close()
        return self._response(text="")

    async def _handle_nodes_get(self, request):
        req = _RequestAdapter(request)
        key = request.match_info["key"]
        try:
            params = requireParams(req, ("nodeID", "Ku_e", "Ku_n", "port"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by kFINDNODE" % exc.args[0])

        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        if req_ku.id() != params["nodeID"]:
            return self._response(status=400, text="requesting node's ID and public key do not match")

        kclosest = self.node.config.routing.findNode(fdecode(key))
        notclose = list(set(self.node.config.routing.knownExternalNodes()) - set(kclosest))
        if len(notclose) > 0 and len(kclosest) > 1:
            kclosest.append(random.choice(notclose))

        updateNode(
            self.node.client,
            self.node.config,
            getCanonicalIP(req.getClientIP()),
            int(params["port"]),
            req_ku,
            params["nodeID"],
        )
        return self._response(text="{'id': '%s', 'k': %s}" % (self.node.config.nodeID, kclosest))

    async def _handle_meta_put(self, request):
        req = _RequestAdapter(request)
        key = request.match_info["key"]
        val = request.match_info["val"]
        try:
            params = requireParams(req, ("nodeID", "Ku_e", "Ku_n", "port"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by kSTORE" % exc.args[0])

        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        if req_ku.id() != params["nodeID"]:
            return self._response(status=400, text="requesting node's ID and public key do not match")

        updateNode(
            self.node.client,
            self.node.config,
            getCanonicalIP(req.getClientIP()),
            int(params["port"]),
            req_ku,
            params["nodeID"],
        )
        fname = os.path.join(self.node.config.kstoredir, key)
        md = fdecode(val)
        with open(fname, "wb") as f:
            f.write(fencode(md).encode("utf-8"))
        return self._response(text="")

    async def _handle_meta_get(self, request):
        req = _RequestAdapter(request)
        key = request.match_info["key"]
        try:
            params = requireParams(req, ("nodeID", "Ku_e", "Ku_n", "port"))
        except Exception as exc:
            return self._response(status=400, text="%s in request received by kFINDVALUE" % exc.args[0])

        req_ku = {"e": int(params["Ku_e"]), "n": int(params["Ku_n"])}
        req_ku = FludRSA.importPublicKey(req_ku)
        if req_ku.id() != params["nodeID"]:
            return self._response(status=400, text="requesting node's ID and public key do not match")

        updateNode(
            self.node.client,
            self.node.config,
            getCanonicalIP(req.getClientIP()),
            int(params["port"]),
            req_ku,
            params["nodeID"],
        )
        fname = os.path.join(self.node.config.kstoredir, key)
        if os.path.isfile(fname):
            with open(fname, "rb") as f:
                data = f.read()
            if not data:
                return self._response(text="")
            d = fdecode(data)
            if isinstance(d, dict) and params["nodeID"] in d:
                resp = {"b": d["b"], params["nodeID"]: d[params["nodeID"]]}
            else:
                resp = d
            return self._response(body=fencode(resp).encode("utf-8"), headers={"nodeID": str(self.node.config.nodeID), "Content-Type": "application/x-flud-data"})

        body = "{'id': '%s', 'k': %s}" % (self.node.config.nodeID, self.node.config.routing.findNode(fdecode(key)))
        return self._response(body=body.encode("utf-8"), headers={"Content-Type": "application/x-flud-nodes"})

    def _create_app(self):
        app = web.Application(client_max_size=1024**3)
        app.router.add_get("/", self._handle_root)
        app.router.add_get("/ID", self._handle_id)

        app.router.add_post("/file/{filekey}", self._handle_file_post)
        app.router.add_get("/file/{filekey}", self._handle_file_get)
        app.router.add_delete("/file/{filekey}", self._handle_file_delete)
        app.router.add_get("/hash/{filekey}", self._handle_hash_get)

        app.router.add_get("/nodes/{key}", self._handle_nodes_get)
        app.router.add_get("/meta/{key}", self._handle_meta_get)
        app.router.add_put("/meta/{key}/{val}", self._handle_meta_put)
        return app

    async def _serve(self):
        self._local_server = AsyncLocalServer(self.node)
        await self._local_server.start()
        app = self._create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host="0.0.0.0", port=self.port)
        await self._site.start()
        logger.info("aiohttp server listening on %d", self.port)
        await self._stop_event.wait()
        if self._local_server is not None:
            await self._local_server.stop()
        await self._runner.cleanup()

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        self._loop.run_until_complete(self._serve())
        self._loop.close()

    def stop(self):
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
