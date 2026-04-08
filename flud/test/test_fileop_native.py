import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from zlib import crc32

import pytest

pytest.importorskip("Cryptodome.Cipher")

import flud.FludFileOperations as fileops
from flud.fencode import fdecode
from flud.test._primitive_data import create_case_file


pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings(
        "ignore:unread_data\\(\\) is deprecated and will be removed in future releases "
        "\\(#3260\\):DeprecationWarning:aiohttp\\.multipart"
    ),
]


@dataclass
class FileOpCases:
    small: list[str]
    large: list[str]
    small_duplicates: list[str]
    large_duplicates: list[str]

    @property
    def all_paths(self):
        return self.small + self.large + self.small_duplicates + self.large_duplicates


def _run(awaitable):
    return asyncio.run(awaitable)


def _gather(awaitables):
    async def _collect():
        return await asyncio.gather(*awaitables)

    return asyncio.run(_collect())


def _list_meta(config):
    with open(os.path.join(config.metadir, config.manifest_name), "r") as handle:
        manifest = handle.read()
    if manifest == "":
        return {}
    return fdecode(manifest)


def _crc32(path):
    value = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            value = crc32(chunk, value)
    return value & 0xFFFFFFFF


def _store_many(node, paths):
    return _gather([fileops.store_file(node, path) for path in paths])


def _retrieve_file(node, path):
    return _run(fileops.retrieve_filename(node, path))


def _assert_round_trip(node, path):
    retrieved = _retrieve_file(node, path)
    saved_path = retrieved[0] if isinstance(retrieved, (list, tuple)) else retrieved
    assert os.path.exists(saved_path)
    assert _crc32(path) == _crc32(saved_path)


@pytest.fixture
def fileop_cases():
    case_dir = Path(tempfile.mkdtemp(prefix="ffot-", dir="/tmp"))
    try:
        small_one = create_case_file(case_dir, 5120, "small-one").path
        small_two = create_case_file(case_dir, 5120, "small-two").path
        small_dup = f"{small_two}.dup"
        shutil.copy(small_two, small_dup)

        large_one = create_case_file(case_dir, 513000, "large-one").path
        large_two = create_case_file(case_dir, 513000, "large-two").path
        large_dup = f"{large_two}.dup"
        shutil.copy(large_two, large_dup)

        yield FileOpCases(
            small=[small_one, small_two],
            large=[large_one, large_two],
            small_duplicates=[small_two, small_dup],
            large_duplicates=[large_two, large_dup],
        )
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


@pytest.fixture
def stored_fileops(flud_cluster, fileop_cases):
    node = flud_cluster.client
    _store_many(node, fileop_cases.small)
    _store_many(node, fileop_cases.large)
    _store_many(node, fileop_cases.small_duplicates)
    _store_many(node, fileop_cases.large_duplicates)
    return fileop_cases


def test_native_fileops_store_updates_master_metadata(flud_cluster, stored_fileops):
    master = _list_meta(flud_cluster.client.config)
    for path in stored_fileops.all_paths:
        assert path in master


def test_native_fileops_retrieve_round_trips_unique_small(flud_cluster, stored_fileops):
    for path in stored_fileops.small:
        _assert_round_trip(flud_cluster.client, path)


def test_native_fileops_retrieve_round_trips_unique_large(flud_cluster, stored_fileops):
    for path in stored_fileops.large:
        _assert_round_trip(flud_cluster.client, path)


def test_native_fileops_retrieve_round_trips_duplicate_small(flud_cluster, stored_fileops):
    for path in stored_fileops.small_duplicates:
        _assert_round_trip(flud_cluster.client, path)


def test_native_fileops_retrieve_round_trips_duplicate_large(flud_cluster, stored_fileops):
    for path in stored_fileops.large_duplicates:
        _assert_round_trip(flud_cluster.client, path)


def test_native_fileops_same_path_double_store(flud_cluster, fileop_cases):
    path = fileop_cases.small[0]
    node = flud_cluster.client

    _run(fileops.store_file(node, path))
    _run(fileops.store_file(node, path))

    master = _list_meta(node.config)
    assert path in master
    _assert_round_trip(node, path)
