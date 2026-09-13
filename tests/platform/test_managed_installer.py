from pathlib import Path

import pytest

from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_installer import FilesystemManagedInstaller
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.managed_update_fs import read_json


class _Signer:
    def sign(self, manifest: bytes) -> bytes:
        return b"synthetic:" + manifest[:16]


class _Verifier:
    def verify(self, manifest_path, signature_path, *, key_id):
        return None


class _Builder:
    def __init__(self, install_root: Path) -> None:
        self.install_root = install_root
        self.requests = []

    def build(self, request):
        self.requests.append(request)
        assert not (self.install_root / "install-state.json").exists()
        assert not (self.install_root / "managed-install.json").exists()
        python = request.candidate_root / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        return CandidateEnvironment(
            request.candidate_root,
            python,
            request.candidate_root / request.entrypoint,
            request.expected_version,
        )


class _FailingBuilder:
    def build(self, request):
        raise RuntimeError("candidate build failed")


def _command(tmp_path: Path) -> InstallManagedCommand:
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('installed')\n", encoding="utf-8")
    (wheelhouse / "clipai.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==2.0\n", encoding="utf-8")
    built = ManagedReleaseBuilder(_Signer()).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=lock,
        output_path=tmp_path / "external-release.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.11",
        key_id="release-key",
    )
    base_python = (tmp_path / "base-python.exe").resolve()
    base_python.write_bytes(b"")
    return InstallManagedCommand(
        shared_root=shared_root,
        install_root=install_root,
        transaction_id=transaction_id("tx-install"),
        expected_version="2.0",
        bundle_path=built.bundle_path,
        bundle_size=built.bundle_size,
        bundle_sha256=built.bundle_sha256,
        manifest_sha256=built.manifest_sha256,
        key_id="release-key",
        managed_install_id="managed-1",
        launcher_version="1.0",
        base_python=base_python,
    )


def test_initial_installer_publishes_identity_only_after_verified_candidate(tmp_path: Path):
    command = _command(tmp_path)
    builder = _Builder(command.install_root)
    installer = FilesystemManagedInstaller(
        manifest_verifier=_Verifier(),
        candidate_builder=builder,
    )

    candidate = installer.install(command)

    assert candidate.root == command.install_root / "versions" / "2.0"
    assert candidate.entrypoint.read_text(encoding="utf-8") == "print('installed')\n"
    assert builder.requests[0].base_python == command.base_python
    state = read_json(command.install_root / "install-state.json")
    marker = read_json(command.install_root / "managed-install.json")
    assert (state["revision"], state["current_version"], state["previous_version"]) == (0, "2.0", None)
    assert marker["managed_install_id"] == "managed-1"
    assert marker["key_id"] == "release-key"
    admitted = command.shared_root / "managed-update" / "transactions" / "tx-install" / "install-bundle.zip"
    assert admitted.is_file()
    assert command.bundle_path.is_file()


def test_initial_installer_removes_partial_version_without_publishing_eligibility(tmp_path: Path):
    command = _command(tmp_path)
    installer = FilesystemManagedInstaller(
        manifest_verifier=_Verifier(),
        candidate_builder=_FailingBuilder(),
    )

    with pytest.raises(ManagedUpdateFailure) as failure:
        installer.install(command)

    assert failure.value.code is FailureCode.PREPARE_FAILED
    assert not (command.install_root / "versions" / "2.0").exists()
    assert not (command.install_root / "install-state.json").exists()
    assert not (command.install_root / "managed-install.json").exists()
