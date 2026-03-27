import asyncio

import pytest

pytest.importorskip("Cryptodome.Cipher")

from flud.fencode import fdecode


pytestmark = pytest.mark.integration

KEY = 87328673569979667228965797330646992089697345905484734072690869757741450870337

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


def _run(coro):
    return asyncio.run(coro)


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


def test_native_sendk_find_node(flud_target):
    response = _run(
        flud_target.node.client.async_sendkFindNode(
            flud_target.host,
            flud_target.port,
            KEY,
        )
    )
    _assert_node_response(response)


def test_native_k_find_node(flud_target):
    response = _run(flud_target.node.client.async_kFindNode(KEY))
    _assert_node_response(response)


def test_native_sendk_store_and_k_store(flud_target):
    send_result = _run(
        flud_target.node.client.async_sendkStore(
            flud_target.host,
            flud_target.port,
            KEY,
            TESTVAL,
        )
    )
    assert send_result == ""

    recursive_result = _run(flud_target.node.client.async_kStore(KEY, TESTVAL))
    assert recursive_result == ""


def test_native_sendk_find_value_and_k_find_value(flud_target):
    _run(
        flud_target.node.client.async_sendkStore(
            flud_target.host,
            flud_target.port,
            KEY,
            TESTVAL,
        )
    )
    _run(flud_target.node.client.async_kStore(KEY, TESTVAL))

    send_result = _run(
        flud_target.node.client.async_sendkFindValue(
            flud_target.host,
            flud_target.port,
            KEY,
        )
    )
    decoded_send = _decode_if_needed(send_result)
    assert isinstance(decoded_send, (dict, str))

    recursive_result = _run(flud_target.node.client.async_kFindValue(KEY))
    assert _decode_if_needed(recursive_result) == TESTVAL
