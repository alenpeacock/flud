import asyncio
import random

import pytest

pytest.importorskip("Cryptodome.Cipher")

from flud.fencode import fdecode


pytestmark = [pytest.mark.integration, pytest.mark.stress, pytest.mark.slow]

TESTVAL = {
    (0, 802484): 465705,
    (1, 780638): 465705,
    (2, 169688): 465705,
    (3, 267175): 465705,
    (4, 648636): 465705,
    (5, 838315): 465705,
    (6, 477619): 465705,
    (7, 329906): 465705,
    (8, 610565): 465705,
    (9, 217811): 465705,
    (10, 374124): 465705,
    (11, 357214): 465705,
    (12, 147307): 465705,
    (13, 427751): 465705,
    (14, 927853): 465705,
    (15, 760369): 465705,
    (16, 707029): 465705,
    (17, 479234): 465705,
    (18, 190455): 465705,
    (19, 647489): 465705,
    (20, 620470): 465705,
    (21, 777532): 465705,
    (22, 622383): 465705,
    (23, 573283): 465705,
    (24, 613082): 465705,
    (25, 433593): 465705,
    (26, 584543): 465705,
    (27, 337485): 465705,
    (28, 911014): 465705,
    (29, 594065): 465705,
    (30, 375876): 465705,
    (31, 726818): 465705,
    (32, 835759): 465705,
    (33, 814060): 465705,
    (34, 237176): 465705,
    (35, 538268): 465705,
    (36, 272650): 465705,
    (37, 314058): 465705,
    (38, 257714): 465705,
    (39, 439931): 465705,
    "k": 20,
    "n": 20,
}


async def _gather_stage(awaitables, timeout):
    return await asyncio.gather(
        *(asyncio.wait_for(awaitable, timeout=timeout) for awaitable in awaitables)
    )


def _public_key_fingerprint(key):
    return (int(key.n), int(key.e))


def _decode_if_needed(value):
    try:
        return fdecode(value)
    except (ValueError, TypeError):
        return value


def _assert_node_response(response):
    assert isinstance(response, dict)
    assert "k" in response
    assert isinstance(response["k"], list)
    if "id" in response:
        assert isinstance(response["id"], str)
    if response["k"]:
        candidate = response["k"][0]
        assert isinstance(candidate, tuple)
        assert len(candidate) == 4


@pytest.mark.asyncio
async def test_native_kprimitive_stress_sequence(
    flud_target,
    flud_k_stress_concurrency,
    flud_stress_timeout,
):
    target = flud_target.node.client
    host = flud_target.host
    port = flud_target.port
    testkeys = [random.randrange(2**256) for _ in range(flud_k_stress_concurrency)]
    lookup_keys = [random.randrange(2**256) for _ in range(flud_k_stress_concurrency)]

    id_results = await _gather_stage(
        (target.get_id(host, port) for _ in range(flud_k_stress_concurrency)),
        flud_stress_timeout,
    )
    assert id_results
    nku = id_results[0]
    expected_key = _public_key_fingerprint(nku)
    assert all(_public_key_fingerprint(result) == expected_key for result in id_results)

    send_find_node_results = await _gather_stage(
        (target.send_k_find_node(host, port, key) for key in lookup_keys),
        flud_stress_timeout,
    )
    for response in send_find_node_results:
        _assert_node_response(response)

    find_node_results = await _gather_stage(
        (target.k_find_node(key) for key in lookup_keys),
        flud_stress_timeout,
    )
    for response in find_node_results:
        _assert_node_response(response)

    send_store_results = await _gather_stage(
        (target.send_k_store(host, port, key, TESTVAL) for key in testkeys),
        flud_stress_timeout,
    )
    assert all(result == "" for result in send_store_results)

    store_results = await _gather_stage(
        (target.k_store(key, TESTVAL) for key in testkeys),
        flud_stress_timeout,
    )
    assert all(result == "" for result in store_results)

    send_find_value_results = await _gather_stage(
        (target.send_k_find_value(host, port, key) for key in testkeys),
        flud_stress_timeout,
    )
    for result in send_find_value_results:
        assert _decode_if_needed(result) == TESTVAL

    find_value_results = await _gather_stage(
        (target.k_find_value(key) for key in testkeys),
        flud_stress_timeout,
    )
    for result in find_value_results:
        assert _decode_if_needed(result) == TESTVAL
