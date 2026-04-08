import asyncio
import os
from binascii import crc32
from dataclasses import dataclass

import pytest

pytest.importorskip("Cryptodome.Cipher")

from flud.protocol.FludCommUtil import (
    BadCASKeyException,
    BadRequestException,
    NotFoundException,
)
from flud.test._primitive_data import create_failure_case_file, metadata_for_path


pytestmark = pytest.mark.integration


@dataclass
class PrimitiveFailureData:
    small_key: str
    small_path: str
    small_bad_path: str
    large_key: str
    large_path: str
    large_bad_path: str


def _run(coro):
    return asyncio.run(coro)

@pytest.fixture
def primitive_failure_data(tmp_path):
    small_case = create_failure_case_file(tmp_path, 1024, "small")
    large_case = create_failure_case_file(tmp_path, 512000, "large")
    return PrimitiveFailureData(
        small_key=small_case.filekey,
        small_path=small_case.path,
        small_bad_path=small_case.bad_path,
        large_key=large_case.filekey,
        large_path=large_case.path,
        large_bad_path=large_case.bad_path,
    )


@pytest.fixture
def stored_small_file(flud_target, primitive_failure_data):
    _run(
        flud_target.node.client.store(
            primitive_failure_data.small_path,
            metadata_for_path(primitive_failure_data.small_path),
            flud_target.host,
            flud_target.port,
            flud_target.nku,
        )
    )
    return primitive_failure_data


def test_native_store_bad_key_small(flud_target, primitive_failure_data):
    with pytest.raises(BadCASKeyException):
        _run(
            flud_target.node.client.store(
                primitive_failure_data.small_bad_path,
                metadata_for_path(primitive_failure_data.small_bad_path),
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_store_bad_key_large(flud_target, primitive_failure_data):
    with pytest.raises(BadCASKeyException):
        _run(
            flud_target.node.client.store(
                primitive_failure_data.large_bad_path,
                metadata_for_path(primitive_failure_data.large_bad_path),
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_retrieve_not_found(flud_target, primitive_failure_data):
    with pytest.raises(NotFoundException):
        _run(
            flud_target.node.client.retrieve(
                primitive_failure_data.large_key,
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_retrieve_illegal_path(flud_target, primitive_failure_data):
    with pytest.raises(NotFoundException):
        _run(
            flud_target.node.client.retrieve(
                os.path.join("somedir", primitive_failure_data.small_key),
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_verify_not_found(flud_target, primitive_failure_data):
    with pytest.raises(NotFoundException):
        _run(
            flud_target.node.client.verify(
                primitive_failure_data.large_key,
                10,
                10,
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_verify_bad_offset(flud_target, stored_small_file):
    fsize = os.stat(stored_small_file.small_path).st_size
    with pytest.raises(BadRequestException):
        _run(
            flud_target.node.client.verify(
                stored_small_file.small_key,
                fsize + 2,
                20,
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_verify_bad_length(flud_target, stored_small_file):
    fsize = os.stat(stored_small_file.small_path).st_size
    with pytest.raises(BadRequestException):
        _run(
            flud_target.node.client.verify(
                stored_small_file.small_key,
                fsize - 10,
                20,
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_verify_bad_key(flud_target, stored_small_file):
    fsize = os.stat(stored_small_file.small_path).st_size
    with pytest.raises(NotFoundException):
        _run(
            flud_target.node.client.verify(
                os.path.basename(stored_small_file.small_bad_path),
                fsize - 20,
                5,
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )


def test_native_delete_bad_key(flud_target, primitive_failure_data):
    bad_key = os.path.join("somedir", primitive_failure_data.large_key)
    with pytest.raises(NotFoundException):
        _run(
            flud_target.node.client.delete(
                bad_key,
                crc32(bad_key.encode("utf-8")),
                flud_target.host,
                flud_target.port,
                flud_target.nku,
            )
        )
