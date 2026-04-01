import tarfile
from pathlib import Path

import pytest
from Cryptodome.Hash import SHA256

from flud.TarfileUtils import concatenate, delete, gzipTarball, verifyHashes
from flud.fencode import fencode


def _write_payload(path, size, fill=b"a"):
    path.write_bytes(fill * size)


def _hashed_name_for_path(path):
    digest = SHA256.new()
    with path.open("rb") as handle:
        digest.update(handle.read())
    return fencode(int(digest.hexdigest(), 16))


def _make_tarball(tmp_path, name, numfiles, avgsize, hashnames=False, addmetas=False):
    tarball_path = tmp_path / f"{name}.tar"
    payload_paths = []
    expected_names = []

    metadata_path = tmp_path / f"{name}.meta-src"
    if addmetas:
        metadata_path.write_text("m" * 48)

    with tarfile.open(tarball_path, "w") as archive:
        for index in range(numfiles):
            size = int(avgsize * (0.5 + ((index + 1) / (numfiles + 1))))
            payload_path = tmp_path / f"{name}-{index}.bin"
            _write_payload(payload_path, size)
            payload_paths.append(payload_path)

            arcname = payload_path.name
            if hashnames:
                arcname = _hashed_name_for_path(payload_path)

            archive.add(payload_path, arcname)
            expected_names.append(arcname)

            if addmetas:
                meta_name = f"{arcname}.343434.meta"
                archive.add(metadata_path, meta_name)
                expected_names.append(meta_name)

    return tarball_path, expected_names


def _archive_names(tarball_path):
    with tarfile.open(tarball_path, "r") as archive:
        return archive.getnames()


@pytest.mark.parametrize("gzipped", [False, True], ids=["plain", "gz"])
def test_native_tarfile_delete_removes_selected_members(tmp_path, gzipped):
    tarball_path, names = _make_tarball(tmp_path, "delete", 5, 4096)
    if gzipped:
        tarball_path = gzipTarball(str(tarball_path))
    else:
        tarball_path = str(tarball_path)

    removed = delete(tarball_path, names[2:4])

    assert removed == names[2:4]
    assert _archive_names(tarball_path) == names[:2] + names[4:]


@pytest.mark.parametrize(
    ("left_gz", "right_gz"),
    [
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ],
    ids=["plain-plain", "gz-plain", "plain-gz", "gz-gz"],
)
def test_native_tarfile_concatenate_preserves_member_order(tmp_path, left_gz, right_gz):
    left_path, left_names = _make_tarball(tmp_path, "left", 5, 4096)
    right_path, right_names = _make_tarball(tmp_path, "right", 5, 4096)

    left_tarball = str(left_path)
    right_tarball = str(right_path)
    if left_gz:
        left_tarball = gzipTarball(left_tarball)
    if right_gz:
        right_tarball = gzipTarball(right_tarball)

    concatenate(left_tarball, right_tarball)

    assert not Path(right_tarball).exists()
    assert _archive_names(left_tarball) == left_names + right_names


@pytest.mark.parametrize("gzipped", [False, True], ids=["plain", "gz"])
@pytest.mark.parametrize("addmetas", [False, True], ids=["no-meta", "with-meta"])
def test_native_tarfile_verify_hashes_accepts_valid_members(tmp_path, gzipped, addmetas):
    tarball_path, names = _make_tarball(
        tmp_path,
        f"verify-{gzipped}-{addmetas}",
        5,
        4096,
        hashnames=True,
        addmetas=addmetas,
    )
    tarball = str(tarball_path)
    if gzipped:
        tarball = gzipTarball(tarball)

    verified = verifyHashes(tarball)

    expected = [name for name in names if not name.endswith(".meta")]
    assert verified == expected


def test_native_tarfile_verify_hashes_rejects_corrupt_gzip(tmp_path):
    tarball_path = tmp_path / "bad.tar.gz"
    tarball_path.write_bytes(b"not a gzip stream")

    assert verifyHashes(str(tarball_path)) == []
