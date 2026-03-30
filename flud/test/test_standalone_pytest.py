"""Pytest bridge for legacy standalone suites that remain script-driven."""

from importlib import import_module

import pytest

from flud.test._standalone import run_status_or_raise


LEGACY_SUITES = [
    pytest.param("FludPrimitiveTestFailure", id="primitive-failure-legacy"),
]


def _run_suite(module_name, flud_host):
    pytest.importorskip("Cryptodome.Cipher")
    module = import_module(f"flud.test.{module_name}")
    status = module.runTests(flud_host)
    run_status_or_raise(status)


@pytest.mark.integration
@pytest.mark.parametrize("module_name", LEGACY_SUITES)
def test_legacy_standalone_suite(module_name, flud_host):
    _run_suite(module_name, flud_host)
