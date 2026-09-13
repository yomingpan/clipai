from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_install import ManagedInstallLayout
from ClipAI.platform.managed_update_fs import atomic_write_json, read_json


class Verifier:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, str]] = []

    def verify(self, manifest_path, signature_path, *, key_id):
        self.calls.append((Path(manifest_path), Path(signature_path), key_id))


def _write_install(tmp_path: Path) -> tuple[ManagedInstallLayout, Verifier, UpdateRequestArtifact]:
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    current_root = install_root / "versions" / "1.0"
    python = current_root / ".venv" / "Scripts" / "python.exe"
    site_packages = current_root / ".venv" / "Lib" / "site-packages"
    python.parent.mkdir(parents=True)
    distribution = site_packages / "clipai-1.0.dist-info"
    distribution.mkdir(parents=True)
    python.write_bytes(b"")
    (distribution / "METADATA").write_text("Metadata-Version: 2.1\nName: ClipAI\nVersion: 1.0\n", encoding="utf-8")
    (current_root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    atomic_write_json(current_root / "install-manifest.json", {
        "schema_version": 1,
        "app_version": "1.0",
        "bundle_format": "clipai-managed-v1",
        "entrypoint": "app.py",
        "python_requires": ">=3.11",
        "requirements_lock_sha256": "a" * 64,
        "files": [
            {"path": "app.py", "size": 12, "sha256": "b" * 64, "role": "payload"},
            {"path": "requirements.lock", "size": 0, "sha256": "a" * 64, "role": "metadata"},
            {"path": "wheelhouse/clipai.whl", "size": 0, "sha256": "c" * 64, "role": "wheel"},
        ],
        "signing_namespace": "clipai.managed-update.manifest.v1",
        "key_id": "release-key",
    })
    atomic_write_json(install_root / "managed-install.json", {
        "schema_version": 1,
        "marker_kind": "clipai-managed-install-v1",
        "managed_install_id": "managed-1",
        "install_root": str(install_root),
        "shared_root": str(shared_root),
        "launcher_version": "1.0",
        "key_id": "release-key",
    })
    atomic_write_json(install_root / "install-state.json", {
        "schema_version": 1,
        "state_kind": "clipai-managed-install-state-v1",
        "managed_install_id": "managed-1",
        "revision": 0,
        "current_version": "1.0",
        "previous_version": None,
    })
    verifier = Verifier()
    layout = ManagedInstallLayout(
        install_root=install_root,
        shared_root=shared_root,
        manifest_verifier=verifier,
    )
    request = UpdateRequestArtifact(
        transaction_id=transaction_id("tx-1"),
        created_at="2026-09-13T00:00:00+00:00",
        installed_version="1.0",
        target_version="2.0",
        installed_executable=python,
        bundle_path=(tmp_path / "bundle.zip").resolve(),
        bundle_size=42,
        bundle_sha256="d" * 64,
        manifest_sha256="e" * 64,
        key_id="release-key",
        install_root=install_root,
        shared_root=shared_root,
        managed_install_id="managed-1",
    )
    return layout, verifier, request


def test_managed_receipt_and_signed_version_are_eligible_only_for_exact_running_executable(tmp_path: Path):
    layout, verifier, request = _write_install(tmp_path)
    state = layout.assert_update_eligible(request)
    assert state.current_version == "1.0"
    assert verifier.calls == [
        (layout.version_root("1.0") / "install-manifest.json", layout.version_root("1.0") / "install-manifest.json.sig", "release-key"),
    ]

    wrong = UpdateRequestArtifact(**{**request.__dict__, "installed_executable": request.installed_executable.with_name("pythonw.exe")})
    with pytest.raises(ManagedUpdateFailure) as raised:
        layout.assert_update_eligible(wrong)
    assert raised.value.code is FailureCode.IDENTITY_INELIGIBLE


def test_source_checkout_and_editable_install_are_ineligible(tmp_path: Path):
    layout, _, request = _write_install(tmp_path)
    (layout.version_root("1.0") / ".git").mkdir()
    with pytest.raises(ManagedUpdateFailure) as source:
        layout.assert_update_eligible(request)
    assert source.value.code is FailureCode.IDENTITY_INELIGIBLE

    (layout.version_root("1.0") / ".git").rmdir()
    direct_url = layout.version_root("1.0") / ".venv" / "Lib" / "site-packages" / "clipai-1.0.dist-info" / "direct_url.json"
    atomic_write_json(direct_url, {"dir_info": {"editable": True}, "url": "file:///source"})
    with pytest.raises(ManagedUpdateFailure) as editable:
        layout.assert_update_eligible(request)
    assert editable.value.code is FailureCode.IDENTITY_INELIGIBLE


def test_commit_and_rollback_atomically_advance_single_pointer_and_retain_old_version(tmp_path: Path):
    layout, _, request = _write_install(tmp_path)
    layout.assert_update_eligible(request)
    candidate_root = layout.version_root("2.0")
    candidate_root.mkdir(parents=True)
    candidate = CandidateEnvironment(candidate_root, candidate_root / ".venv" / "Scripts" / "python.exe", candidate_root / "app.py", "2.0")

    receipt = layout.commit(candidate)
    committed = read_json(layout.install_root / "install-state.json")
    assert (committed["revision"], committed["current_version"], committed["previous_version"]) == (1, "2.0", "1.0")
    assert receipt.previous_root.is_dir()

    layout.finalize(receipt)
    assert receipt.previous_root.is_dir()
    layout.rollback(receipt)
    rolled_back = read_json(layout.install_root / "install-state.json")
    assert (rolled_back["revision"], rolled_back["current_version"], rolled_back["previous_version"]) == (2, "1.0", "2.0")


def test_state_and_marker_identity_must_agree_and_roots_must_be_disjoint(tmp_path: Path):
    layout, _, request = _write_install(tmp_path)
    state_path = layout.install_root / "install-state.json"
    state = read_json(state_path)
    state["managed_install_id"] = "different"
    atomic_write_json(state_path, state)
    with pytest.raises(ManagedUpdateFailure) as mismatch:
        layout.assert_update_eligible(request)
    assert mismatch.value.code is FailureCode.IDENTITY_INELIGIBLE

    state["managed_install_id"] = "managed-1"
    atomic_write_json(state_path, state)
    marker_path = layout.install_root / "managed-install.json"
    marker = read_json(marker_path)
    marker["shared_root"] = str(layout.install_root / "user-data")
    atomic_write_json(marker_path, marker)
    nested_layout = ManagedInstallLayout(
        install_root=layout.install_root,
        shared_root=layout.install_root / "user-data",
        manifest_verifier=Verifier(),
    )
    nested_request = UpdateRequestArtifact(**{**request.__dict__, "shared_root": layout.install_root / "user-data"})
    with pytest.raises(ManagedUpdateFailure) as overlap:
        nested_layout.assert_update_eligible(nested_request)
    assert overlap.value.code is FailureCode.IDENTITY_INELIGIBLE
