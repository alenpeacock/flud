"""Pytest bridge for legacy standalone suites that remain script-driven."""

from importlib import import_module

import pytest

from flud.test._standalone import run_status_or_raise


LEGACY_SUITES = [
    pytest.param("FludPrimitiveTest", id="primitive-legacy"),
    pytest.param("FludkPrimitiveTest", id="kprimitive-legacy"),
    pytest.param("FludPrimitiveTestFailure", id="primitive-failure-legacy"),
]

STRESS_SUITES = [
    pytest.param(
        "FludPrimitiveStressTest",
        marks=(pytest.mark.slow, pytest.mark.stress),
        id="primitive-stress",
    ),
    pytest.param(
        "FludkPrimitiveStressTest",
        marks=(pytest.mark.slow, pytest.mark.stress),
        id="kprimitive-stress",
    ),
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


@pytest.mark.integration
@pytest.mark.parametrize("module_name", STRESS_SUITES)
def test_legacy_stress_suite(module_name, flud_host):
    _run_suite(module_name, flud_host)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.stress
def test_legacy_stress_sequence(flud_host):
    for suite in STRESS_SUITES:
        _run_suite(suite.values[0], flud_host)
