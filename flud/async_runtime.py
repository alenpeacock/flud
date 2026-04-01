import asyncio
import concurrent.futures
import logging
import os
import sys
import threading
import time

try:
    import aiohttp
except Exception:  # pragma: no cover - optional at runtime
    aiohttp = None

from flud.defer import Deferred

logger = logging.getLogger("flud.async_runtime")
httplogger = logging.getLogger("flud.async_http")


def _diag_enabled():
    return os.environ.get("FLUD_ASYNC_DIAG") == "1"


def deferred_to_future_threadsafe(deferred, loop=None):
    if loop is None:
        loop = asyncio.get_running_loop()
    future = loop.create_future()

    def _set_result(result):
        if not future.done():
            future.set_result(result)

    def _set_exception(exc):
        if not future.done():
            future.set_exception(exc)

    def _callback(result):
        loop.call_soon_threadsafe(_set_result, result)
        return result

    def _errback(err):
        exc = getattr(err, "value", err)
        loop.call_soon_threadsafe(_set_exception, exc)
        return None

    deferred.addCallbacks(_callback, _errback)
    return future


async def maybe_await(result, loop=None):
    if hasattr(result, "addCallbacks"):
        return await deferred_to_future_threadsafe(result, loop=loop)
    if asyncio.isfuture(result) or asyncio.iscoroutine(result):
        return await result
    return result


def concurrent_future_to_deferred(future):
    deferred = Deferred()

    def _deliver_result(result):
        if not deferred.called:
            deferred.callback(result)

    def _deliver_error(exc):
        if not deferred.called:
            deferred.errback(exc)

    def _done(done_future):
        try:
            result = done_future.result()
        except Exception as exc:
            _deliver_error(exc)
            return
        _deliver_result(result)

    future.add_done_callback(_done)
    return deferred


class AsyncRuntime:
    def __init__(self, name="flud-async-runtime"):
        self._name = name
        self._thread = None
        self._thread_id = None
        self._loop = None
        self._ready = threading.Event()

    def start(self):
        if self._thread is not None:
            return

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._thread_id = threading.get_ident()
            self._ready.set()
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

        self._thread = threading.Thread(target=_run, name=self._name, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)

    @property
    def loop(self):
        self.start()
        return self._loop

    def submit(self, coro):
        self.start()
        if self.in_runtime_thread():
            if _diag_enabled():
                logger.warning("submit called from runtime thread; scheduling task inline")
            future = concurrent.futures.Future()
            task = asyncio.create_task(coro)

            def _copy_result(done_task):
                try:
                    future.set_result(done_task.result())
                except Exception as exc:
                    future.set_exception(exc)

            task.add_done_callback(_copy_result)
            return future
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def deferred_from_coro(self, coro):
        return concurrent_future_to_deferred(self.submit(coro))

    def stop(self):
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        self._thread_id = None
        self._loop = None
        self._ready.clear()

    def in_runtime_thread(self):
        return self._thread_id is not None and threading.get_ident() == self._thread_id


class AsyncHTTPClient:
    def __init__(self, runtime):
        self.runtime = runtime
        self._session = None
        self._session_lock = None

    async def _get_session(self):
        if aiohttp is None:
            raise RuntimeError("aiohttp is not available")
        if self._session_lock is None:
            self._session_lock = asyncio.Lock()
        async with self._session_lock:
            if self._session is None or self._session.closed:
                connector_kwargs = dict(
                    limit=80,
                    limit_per_host=20,
                    ttl_dns_cache=300,
                    force_close=True,
                )
                if sys.version_info < (3, 14, 3):
                    connector_kwargs["enable_cleanup_closed"] = True
                connector = aiohttp.TCPConnector(**connector_kwargs)
                self._session = aiohttp.ClientSession(connector=connector)
            return self._session

    async def request(self, method, url, **kwargs):
        session = await self._get_session()
        start = time.monotonic()
        if _diag_enabled():
            httplogger.warning("request start %s %s", method, url)
        try:
            response = await session.request(method, url, **kwargs)
        except Exception:
            httplogger.exception("request failed %s %s", method, url)
            raise
        if _diag_enabled():
            httplogger.warning("request ready %s %s -> %s in %.3fs",
                    method, url, response.status, time.monotonic() - start)
        return response

    async def _close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def close(self):
        if self.runtime.loop is None:
            return
        future = self.runtime.submit(self._close())
        future.result(timeout=5.0)
