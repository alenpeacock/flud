#!/usr/bin/env python3

"""Helpers for standalone integration scripts in ``flud.test``."""

import socket
import sys


def normalize_failure(error, message=None):
    """Convert deferred/failure objects into an exception instance."""
    candidate = getattr(error, "value", error)
    if isinstance(candidate, BaseException):
        if message:
            return RuntimeError(f"{message}: {candidate}")
        return candidate

    text = str(error)
    if message:
        text = f"{message}: {text}"
    return RuntimeError(text)


class SuiteStatus:
    def __init__(self, name):
        self.name = name
        self.failed = False
        self.succeeded = False
        self.error = None
        self.value = None

    def record_failure(self, error, message=None):
        exc = normalize_failure(error, message)
        self.failed = True
        if self.error is None:
            self.error = exc
        return exc

    def record_success(self, value=None):
        if not self.failed:
            self.succeeded = True
            self.value = value
        return value

    def exit_code(self):
        if self.failed:
            return 1
        if self.succeeded:
            return 0
        self.record_failure(RuntimeError(f"{self.name} did not report success"))
        return 1


def run_status_or_raise(status):
    """Raise the captured suite error so pytest gets a real failure."""
    if status.exit_code() == 0:
        return status.value
    error = status.error or RuntimeError(f"{status.name} failed")
    raise error


def parse_cli_args(argv, usage):
    localhost = socket.getfqdn()
    if len(argv) == 1:
        return (localhost,)
    if len(argv) == 2:
        return (localhost, eval(argv[1]))
    if len(argv) == 3:
        return (argv[1], eval(argv[2]))
    if len(argv) == 4:
        return (argv[1], eval(argv[2]), eval(argv[3]))
    raise SystemExit(usage)


def run_cli(run_tests, usage, argv=None):
    argv = argv or sys.argv
    result = run_tests(*parse_cli_args(argv, usage))
    raise SystemExit(result.exit_code())


def start_test_node(listenport=None):
    from flud.FludNode import FludNode

    node = FludNode(port=listenport)
    node.run()
    return node


def suite_port(node, port=None):
    return node.config.port if port is None else port


def attach_suite_status(deferred, suite_status):
    deferred.addCallback(suite_status.record_success)
    deferred.addErrback(lambda failure: suite_status.record_failure(failure))
    return deferred


def join_suite(node, deferred, cleanup, *cleanup_args):
    deferred.addBoth(cleanup, node, *cleanup_args)
    node.join()


def schedule_node_stop(node, delay=0):
    def _stop():
        node.stop()

    node.async_runtime.loop.call_soon_threadsafe(
        lambda: node.async_runtime.loop.call_later(delay, _stop)
    )
