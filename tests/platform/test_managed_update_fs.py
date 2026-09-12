import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from ClipAI.platform.managed_update_fs import (
    ManagedUpdateFileError,
    atomic_write_json,
    extract_prefixed_zip,
    read_json,
    require_contained,
)


def test_atomic_json_round_trip_supports_windows_long_paths(tmp_path: Path):
    deep = tmp_path
    while len(str(deep / "state.json")) < 280:
        deep = deep / "segment0123456789"
    destination = deep / "state.json"
    atomic_write_json(destination, {"version": 1, "value": "ok"})
    assert read_json(destination) == {"value": "ok", "version": 1}


def test_containment_rejects_parent_escape(tmp_path: Path):
    assert require_contained(tmp_path, tmp_path / "child") == tmp_path / "child"
    with pytest.raises(ManagedUpdateFileError, match="escapes"):
        require_contained(tmp_path, tmp_path.parent / "outside")


def test_prefixed_archive_extracts_only_valid_regular_files(tmp_path: Path):
    archive_path = tmp_path / "bundle.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("clipai-managed-v1/payload/main.py", "print('ok')")
        archive.writestr("clipai-managed-v1/requirements.lock", "example==1")
    extracted = extract_prefixed_zip(archive_path, tmp_path / "candidate")
    assert {path.relative_to(tmp_path / "candidate").as_posix() for path in extracted} == {
        "payload/main.py",
        "requirements.lock",
    }


@pytest.mark.parametrize("member", ["payload/main.py", "clipai-managed-v1/../escape"])
def test_prefixed_archive_rejects_wrong_prefix_and_traversal(tmp_path: Path, member: str):
    archive_path = tmp_path / "bad.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(member, json.dumps({"bad": True}))
    with pytest.raises(ManagedUpdateFileError):
        extract_prefixed_zip(archive_path, tmp_path / "candidate")
