import io
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZipFile

import pytest

from scripts import build_setup_release as module


def test_source_binding_does_not_let_payload_hide_changed_wheel_main(tmp_path, monkeypatch):
    source = {"main.py": b"source entry", "ClipAI/app/first_install_bootstrap.py": b"bootstrap"}
    tree = io.BytesIO()
    with tarfile.open(fileobj=tree, mode="w") as archive:
        for name, data in source.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, tree.getvalue(), b""))
    wheel = io.BytesIO()
    with ZipFile(wheel, "w") as archive:
        archive.writestr("main.py", b"substituted wheel entry")
        archive.writestr("ClipAI/app/first_install_bootstrap.py", b"bootstrap")
    bundle = tmp_path / "bundle.zip"
    with ZipFile(bundle, "w") as archive:
        archive.writestr("clipai-managed-v1/wheelhouse/clipai-3.7.8-py3-none-any.whl", wheel.getvalue())
        archive.writestr("clipai-managed-v1/payload/main.py", b"source entry")
    with pytest.raises(ValueError, match="main.py"):
        module.verify_source_commit(bundle, "a" * 40)


def test_short_commit_is_rejected_before_git(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("git must not execute")
    monkeypatch.setattr(module.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="full SHA"):
        module.verify_source_commit(Path("absent"), "HEAD")
