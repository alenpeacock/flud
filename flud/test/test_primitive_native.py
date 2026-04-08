import asyncio

import pytest

pytest.importorskip("Cryptodome.Cipher")

from flud.protocol.FludCommUtil import NotFoundException
from flud.test._primitive_data import (
    FAKE_MKEY_OFFSET,
    create_case_file,
    find_retrieved_metadata,
    find_retrieved_payload,
    metadata_for_key,
    metadata_key,
    sample_verify_range,
    verify_metadata_matches,
    verify_payload_matches,
)


pytestmark = pytest.mark.integration


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(params=[("small", 5120), ("large", 512000)], ids=["small", "large"])
def primitive_case(tmp_path, request):
    size_name, min_size = request.param
    return create_case_file(tmp_path, min_size, size_name)


def _store(flud_target, primitive_case, mkey):
    return _run(
        flud_target.node.client.store(
            primitive_case.path,
            metadata_for_key(mkey),
            flud_target.host,
            flud_target.port,
            flud_target.nku,
        )
    )


def _retrieve(flud_target, primitive_case, metakey=True):
    return _run(
        flud_target.node.client.retrieve(
            primitive_case.filekey,
            flud_target.host,
            flud_target.port,
            flud_target.nku,
            metakey,
        )
    )


def _verify(flud_target, primitive_case, mkey):
    offset, length, expected_hash = sample_verify_range(primitive_case.path)
    result = _run(
        flud_target.node.client.verify(
            primitive_case.filekey,
            offset,
            length,
            flud_target.host,
            flud_target.port,
            flud_target.nku,
            metadata_for_key(mkey),
        )
    )
    assert int(result, 16) == int(expected_hash, 16)


def _delete(flud_target, primitive_case, mkey):
    return _run(
        flud_target.node.client.delete(
            primitive_case.filekey,
            mkey,
            flud_target.host,
            flud_target.port,
            flud_target.nku,
        )
    )


def test_native_store_retrieve_preserves_payload_and_metadata(flud_target, primitive_case):
    mkey = metadata_key(primitive_case.path)
    _store(flud_target, primitive_case, mkey)

    saved_paths = _retrieve(flud_target, primitive_case, mkey)
    payload_path = find_retrieved_payload(saved_paths, primitive_case.filekey)
    metadata_path = find_retrieved_metadata(saved_paths, primitive_case.filekey, mkey)

    assert verify_payload_matches(primitive_case.path, payload_path)
    assert verify_metadata_matches(metadata_path)


def test_native_verify_delete_flow(flud_target, primitive_case):
    original_mkey = metadata_key(primitive_case.path)
    replacement_mkey = original_mkey + (2 * FAKE_MKEY_OFFSET)
    verify_mkey = original_mkey + FAKE_MKEY_OFFSET

    _store(flud_target, primitive_case, original_mkey)
    _store(flud_target, primitive_case, replacement_mkey)

    _verify(flud_target, primitive_case, original_mkey)
    _verify(flud_target, primitive_case, verify_mkey)

    _delete(flud_target, primitive_case, original_mkey)
    saved_paths = _retrieve(flud_target, primitive_case, True)
    payload_path = find_retrieved_payload(saved_paths, primitive_case.filekey)
    assert verify_payload_matches(primitive_case.path, payload_path)

    _delete(flud_target, primitive_case, verify_mkey)
    saved_paths = _retrieve(flud_target, primitive_case, True)
    payload_path = find_retrieved_payload(saved_paths, primitive_case.filekey)
    assert verify_payload_matches(primitive_case.path, payload_path)

    _delete(flud_target, primitive_case, replacement_mkey)
    with pytest.raises(NotFoundException):
        _retrieve(flud_target, primitive_case, True)


def test_native_aggregate_store_small_files(flud_target, tmp_path):
    cases = [create_case_file(tmp_path, 4096, f"agg-{index}") for index in range(4)]

    async def _store_all():
        return await asyncio.gather(
            *(
                flud_target.node.client.store(
                    case.path,
                    metadata_for_key(metadata_key(case.path)),
                    flud_target.host,
                    flud_target.port,
                    flud_target.nku,
                )
                for case in cases
            )
        )

    _run(_store_all())

    for case in cases:
        mkey = metadata_key(case.path)
        saved_paths = _retrieve(flud_target, case, mkey)
        payload_path = find_retrieved_payload(saved_paths, case.filekey)
        metadata_path = find_retrieved_metadata(saved_paths, case.filekey, mkey)

        assert verify_payload_matches(case.path, payload_path)
        assert verify_metadata_matches(metadata_path)
        _verify(flud_target, case, mkey)
