import asyncio
from pathlib import Path

import pytest

pytest.importorskip("Cryptodome.Cipher")

import flud.FludCrypto as FludCrypto
from flud.fencode import fencode


pytestmark = [pytest.mark.integration, pytest.mark.stress, pytest.mark.slow]


async def _gather_stage(awaitables, timeout):
    return await asyncio.gather(
        *(asyncio.wait_for(awaitable, timeout=timeout) for awaitable in awaitables)
    )


def _public_key_fingerprint(key):
    return (int(key.n), int(key.e))


def _create_stress_file(directory, index):
    payload = FludCrypto.generateRandom(256)
    filekey = fencode(int(FludCrypto.hashstring(payload), 16))
    path = Path(directory) / filekey
    while path.exists():
        payload = FludCrypto.generateRandom(256)
        filekey = fencode(int(FludCrypto.hashstring(payload), 16))
        path = Path(directory) / filekey
    path.write_bytes(payload)
    return path


def _verify_downloaded_payloads(source_paths, retrieved_payloads):
    for source_path, retrieved_path in zip(source_paths, retrieved_payloads):
        assert Path(source_path).read_bytes() == Path(retrieved_path).read_bytes()


@pytest.fixture
def primitive_stress_files(tmp_path, flud_primitive_stress_concurrency):
    return [
        _create_stress_file(tmp_path, index)
        for index in range(flud_primitive_stress_concurrency)
    ]


@pytest.mark.asyncio
async def test_native_primitive_stress_sequence(
    flud_target,
    primitive_stress_files,
    flud_stress_timeout,
):
    target = flud_target.node.client
    host = flud_target.host
    port = flud_target.port

    id_results = await _gather_stage(
        (target.async_sendGetID(host, port) for _ in primitive_stress_files),
        flud_stress_timeout,
    )
    assert id_results
    nku = id_results[0]
    expected_key = _public_key_fingerprint(nku)
    assert all(_public_key_fingerprint(result) == expected_key for result in id_results)

    store_results = await _gather_stage(
        (
            target.async_sendStore(
                str(path),
                None,
                host,
                port,
                nku,
            )
            for path in primitive_stress_files
        ),
        flud_stress_timeout,
    )
    assert len(store_results) == len(primitive_stress_files)

    retrieve_results = await _gather_stage(
        (
            target.async_sendRetrieve(
                path.name,
                host,
                port,
                nku,
            )
            for path in primitive_stress_files
        ),
        flud_stress_timeout,
    )
    retrieved_payloads = []
    for source_path, saved_paths in zip(primitive_stress_files, retrieve_results):
        payload_path = next(candidate for candidate in saved_paths if candidate.endswith(source_path.name))
        retrieved_payloads.append(payload_path)
    _verify_downloaded_payloads(primitive_stress_files, retrieved_payloads)

    verify_specs = []
    for path in primitive_stress_files:
        payload = path.read_bytes()
        offset = 0
        length = min(20, len(payload))
        expected_hash = FludCrypto.hashstring(payload[offset : offset + length])
        verify_specs.append((path.name, offset, length, expected_hash))

    verify_results = await _gather_stage(
        (
            target.async_sendVerify(
                filekey,
                offset,
                length,
                host,
                port,
                nku,
            )
            for filekey, offset, length, _ in verify_specs
        ),
        flud_stress_timeout,
    )
    for (_, _, _, expected_hash), result in zip(verify_specs, verify_results):
        assert int(result, 16) == int(expected_hash, 16)
