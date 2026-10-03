from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_install import ManagedInstallLayout, read_stable_launcher_marker
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
        installed_process_id=1234,
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


def test_selfcheck_proves_exact_current_launch_environment_without_an_update_request(tmp_path: Path) -> None:
    layout, verifier, _request = _write_install(tmp_path)

    current = layout.prove_current_install()

    assert current == CandidateEnvironment(
        root=layout.version_root("1.0"),
        python=layout.version_root("1.0") / ".venv" / "Scripts" / "python.exe",
        entrypoint=layout.version_root("1.0") / "app.py",
        version="1.0",
    )
    assert verifier.calls == [
        (layout.version_root("1.0") / "install-manifest.json", layout.version_root("1.0") / "install-manifest.json.sig", "release-key"),
    ]


def test_runtime_update_identity_is_proven_from_exact_current_process(tmp_path: Path) -> None:
    layout, _verifier, request = _write_install(tmp_path)

    proof = layout.prove_update_client(
        executable_path=request.installed_executable,
        process_id=4321,
    )

    assert proof.identity.installed_version == "1.0"
    assert proof.identity.launcher_version == "1.0"
    assert proof.identity.installed_process_id == 4321
    assert proof.identity.install_root == layout.install_root
    assert proof.identity.shared_root == layout.shared_root
    assert proof.current.entrypoint == layout.version_root("1.0") / "app.py"

    with pytest.raises(ManagedUpdateFailure) as wrong:
        layout.prove_update_client(
            executable_path=request.installed_executable.with_name("pythonw.exe"),
            process_id=4321,
        )
    assert wrong.value.code is FailureCode.IDENTITY_INELIGIBLE


def test_keyring_verifier_allows_release_key_rotation_beyond_bootstrap_marker(tmp_path: Path) -> None:
    layout, verifier, request = _write_install(tmp_path)
    rotated_request = UpdateRequestArtifact(**{**request.__dict__, "key_id": "release-key-rotated"})

    assert layout.assert_update_eligible(rotated_request).current_version == "1.0"

    rotated_root = layout.version_root("2.0")
    rotated_python = rotated_root / ".venv" / "Scripts" / "python.exe"
    rotated_metadata = rotated_root / ".venv" / "Lib" / "site-packages" / "clipai-2.0.dist-info" / "METADATA"
    rotated_python.parent.mkdir(parents=True)
    rotated_metadata.parent.mkdir(parents=True)
    rotated_python.write_bytes(b"")
    rotated_metadata.write_text("Metadata-Version: 2.1\nName: ClipAI\nVersion: 2.0\n", encoding="utf-8")
    (rotated_root / "app.py").write_text("print('rotated')\n", encoding="utf-8")
    atomic_write_json(rotated_root / "install-manifest.json", {
        "schema_version": 1, "app_version": "2.0", "bundle_format": "clipai-managed-v1",
        "entrypoint": "app.py", "python_requires": ">=3.11",
        "requirements_lock_sha256": "a" * 64,
        "files": [
            {"path": "app.py", "size": 17, "sha256": "b" * 64, "role": "payload"},
            {"path": "requirements.lock", "size": 0, "sha256": "a" * 64, "role": "metadata"},
            {"path": "wheelhouse/clipai.whl", "size": 0, "sha256": "c" * 64, "role": "wheel"},
        ],
        "signing_namespace": "clipai.managed-update.manifest.v1", "key_id": "release-key-rotated",
    })
    atomic_write_json(layout.install_root / "install-state.json", {
        "schema_version": 1, "state_kind": "clipai-managed-install-state-v1",
        "managed_install_id": "managed-1", "revision": 1,
        "current_version": "2.0", "previous_version": "1.0",
    })

    assert layout.prove_current_install().version == "2.0"
    assert verifier.calls[-1][2] == "release-key-rotated"


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


def test_recovery_restores_target_pointer_to_signed_known_good_version(tmp_path: Path) -> None:
    layout, verifier, request = _write_install(tmp_path)
    atomic_write_json(layout.install_root / "install-state.json", {
        "schema_version": 1,
        "state_kind": "clipai-managed-install-state-v1",
        "managed_install_id": "managed-1",
        "revision": 1,
        "current_version": "2.0",
        "previous_version": "1.0",
    })

    known_good = layout.restore_known_good(request)

    assert known_good.version == "1.0"
    recovered = read_json(layout.install_root / "install-state.json")
    assert (recovered["revision"], recovered["current_version"], recovered["previous_version"]) == (2, "1.0", "2.0")
    assert verifier.calls[-1][2] == "release-key"


def test_recovery_is_noop_when_known_good_pointer_is_already_active(tmp_path: Path) -> None:
    layout, _, request = _write_install(tmp_path)

    known_good = layout.restore_known_good(request)

    assert known_good.version == "1.0"
    state = read_json(layout.install_root / "install-state.json")
    assert (state["revision"], state["current_version"], state["previous_version"]) == (0, "1.0", None)


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


def test_only_fixed_launcher_root_discovers_the_managed_marker(tmp_path: Path) -> None:
    layout, _, _ = _write_install(tmp_path)
    launcher = layout.install_root / "launcher"
    launcher.mkdir()

    marker = read_stable_launcher_marker(launcher)

    assert marker is not None
    assert marker.install_root == layout.install_root
    assert read_stable_launcher_marker(layout.version_root("1.0")) is None
