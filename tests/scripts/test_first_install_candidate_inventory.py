from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
from zipfile import ZipFile

import pytest

from experiments.first_install import inventory_candidates as inventory


def archive(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as target:
        for name, content in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            target.addfile(member, io.BytesIO(content))
    return path


def test_runtime_profile_excludes_development_site_packages_and_inventory_includes_venv_stub(tmp_path):
    source = archive(tmp_path / "runtime.tar.gz", {
        "python/python.exe": b"base",
        "python/Lib/venv/scripts/nt/python.exe": b"stub",
        "python/Lib/site-packages/foreign.dll": b"foreign",
        "python/LICENSE.txt": b"notice",
    })
    native, notices, _ = inventory.selected_records(source, "runtime")
    assert {row["path"] for row in native} == {"python.exe", "Lib/venv/scripts/nt/python.exe"}
    assert [row["path"] for row in notices] == ["LICENSE.txt"]


def test_bundled_wheel_notice_is_catalogued_without_treating_license_code_as_notice(tmp_path):
    content = io.BytesIO()
    with ZipFile(content, "w") as wheel:
        wheel.writestr("pip.dist-info/LICENSE.txt", b"notice")
        wheel.writestr("pip/_vendor/packaging/licenses/__init__.py", b"code")
    source = archive(tmp_path / "runtime.tar.gz", {
        "python/Lib/ensurepip/_bundled/pip.whl": content.getvalue(),
    })
    _, _, notices = inventory.selected_records(source, "runtime")
    assert [row["path"] for row in notices] == ["pip.dist-info/LICENSE.txt"]


def test_verifier_profile_omits_service_installers_and_server_binaries(tmp_path):
    source = tmp_path / "tools.zip"
    with ZipFile(source, "w") as target:
        for name in ("ssh-keygen.exe", "libcrypto.dll", "sshd.exe", "install-sshd.ps1", "LICENSE.txt", "NOTICE.txt"):
            target.writestr("OpenSSH-Win64/" + name, b"fixture")
    native, notices, _ = inventory.selected_records(source, "verifier")
    assert {row["path"] for row in native} == {"ssh-keygen.exe", "libcrypto.dll"}
    assert {row["path"] for row in notices} == {"LICENSE.txt", "NOTICE.txt"}


def test_unsafe_archive_member_is_rejected_without_extraction(tmp_path):
    source = archive(tmp_path / "runtime.tar.gz", {"python/../escape.exe": b"unsafe"})
    with pytest.raises(ValueError, match="unsafe archive member"):
        inventory.selected_records(source, "runtime")
    assert not (tmp_path / "escape.exe").exists()


def test_changed_unpacked_native_file_is_rejected_before_signature_process(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = archive(candidate / "download.archive", {"python/python.exe": b"admitted"})
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"runtime": {
        "size": source.stat().st_size,
        "sha256": inventory.digest(source.read_bytes()),
    }}), encoding="utf-8")
    monkeypatch.setattr(inventory, "INPUTS", inputs)
    root = candidate / "unpacked/python"
    root.mkdir(parents=True)
    (root / "python.exe").write_bytes(b"modified")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="differs from admitted archive"):
        inventory.inventory("runtime", candidate, output)
    assert not output.exists()
