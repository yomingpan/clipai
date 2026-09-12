from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ClipAI.core.managed_update import CommitReceipt, FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.managed_update_backend import FilesystemManagedUpdateBackend
from ClipAI.platform.managed_update_fs import native_path


class Signer:
    def sign(self, manifest: bytes) -> bytes:
        return b"synthetic:" + manifest[:16]


class Verifier:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.calls: list[tuple[Path, Path, str]] = []

    def verify(self, manifest_path, signature_path, *, key_id):
        self.calls.append((Path(manifest_path), Path(signature_path), key_id))
        if self.fails:
            raise ValueError("invalid signature")


class Layout:
    def __init__(self, install_root: Path, shared_root: Path) -> None:
        self.install_root = install_root
        self.shared_root = shared_root
        self.events: list[str] = []

    def assert_update_eligible(self, request):
        self.events.append("eligible")

    def version_root(self, version: str) -> Path:
        return self.install_root / "versions" / version

    def commit(self, candidate: CandidateEnvironment) -> CommitReceipt:
        self.events.append("commit")
        previous = self.version_root("1.0")
        previous.mkdir(parents=True, exist_ok=True)
        return CommitReceipt(previous, candidate.root)

    def rollback(self, receipt: CommitReceipt) -> None:
        self.events.append("rollback")

    def finalize(self, receipt: CommitReceipt) -> None:
        self.events.append("finalize")


class Builder:
    def __init__(self, *, wrong_evidence: bool = False) -> None:
        self.wrong_evidence = wrong_evidence
        self.requests = []

    def build(self, request):
        self.requests.append(request)
        python = request.candidate_root / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        if self.wrong_evidence:
            python = request.candidate_root / ".venv" / "Scripts" / "pythonw.exe"
        return CandidateEnvironment(
            request.candidate_root,
            python,
            request.candidate_root / request.entrypoint,
            request.expected_version,
        )


def _fixture(tmp_path: Path, *, verifier: Verifier | None = None, builder: Builder | None = None):
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    transaction_root = shared_root / "managed-update" / "transactions" / "tx-1"
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('managed')\n", encoding="utf-8")
    (wheelhouse / "clipai-2.0-py3-none-any.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==2.0\n", encoding="utf-8")
    built = ManagedReleaseBuilder(Signer()).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=lock,
        output_path=transaction_root / "release.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.11",
        key_id="release-key",
    )
    request = UpdateRequestArtifact(
        transaction_id=transaction_id("tx-1"),
        created_at="2026-09-13T00:00:00+00:00",
        installed_version="1.0",
        target_version="2.0",
        installed_executable=install_root / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe",
        bundle_path=built.bundle_path,
        bundle_size=built.bundle_size,
        bundle_sha256=built.bundle_sha256,
        manifest_sha256=built.manifest_sha256,
        key_id="release-key",
        install_root=install_root,
        shared_root=shared_root,
        managed_install_id="managed-1",
    )
    layout = Layout(install_root, shared_root)
    actual_verifier = verifier or Verifier()
    actual_builder = builder or Builder()
    base_python = tmp_path / "base-python.exe"
    base_python.write_bytes(b"")
    backend = FilesystemManagedUpdateBackend(
        layout=layout,  # type: ignore[arg-type]
        manifest_verifier=actual_verifier,
        candidate_builder=actual_builder,
        base_python=base_python,
    )
    return backend, layout, actual_verifier, actual_builder, request


def test_backend_admits_verified_bundle_prepares_offline_candidate_and_retains_old(tmp_path: Path):
    backend, layout, verifier, builder, request = _fixture(tmp_path)
    backend.verify(request)
    candidate = backend.prepare(request)
    assert candidate.root == layout.version_root("2.0")
    assert builder.requests[0].entrypoint == "payload/main.py"
    assert verifier.calls[0][2] == "release-key"
    assert not native_path(candidate.root.parent / ".2.0.candidate-owner.json").exists()

    receipt = backend.commit(candidate)
    backend.finalize(receipt)
    assert layout.events == ["eligible", "commit", "finalize"]
    assert receipt.previous_root.is_dir()
    assert candidate.root.is_dir()
    assert not (request.shared_root / "managed-update" / "transactions" / "tx-1" / "verified-bundle").exists()


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"bundle_size": 1}, FailureCode.DOWNLOAD_FAILED),
        ({"bundle_size": 2 * 1024 * 1024 * 1024 + 1}, FailureCode.DOWNLOAD_FAILED),
        ({"bundle_sha256": "0" * 64}, FailureCode.DOWNLOAD_FAILED),
        ({"manifest_sha256": "0" * 64}, FailureCode.SIGNATURE_INVALID),
    ],
)
def test_backend_fails_closed_on_catalog_bound_identity_mismatch(tmp_path: Path, change: dict, code: FailureCode):
    backend, _, _, builder, request = _fixture(tmp_path)
    with pytest.raises(ManagedUpdateFailure) as raised:
        backend.verify(replace(request, **change))
    assert raised.value.code is code
    assert builder.requests == []


def test_backend_maps_manifest_verification_failure_to_signature_code(tmp_path: Path):
    verifier = Verifier(fails=True)
    backend, _, _, _, request = _fixture(tmp_path, verifier=verifier)
    with pytest.raises(ManagedUpdateFailure) as raised:
        backend.verify(request)
    assert raised.value.code is FailureCode.SIGNATURE_INVALID


def test_prepare_never_deletes_foreign_target_version_root(tmp_path: Path):
    backend, layout, _, builder, request = _fixture(tmp_path)
    backend.verify(request)
    target = layout.version_root("2.0")
    target.mkdir(parents=True)
    sentinel = target / "keep.txt"
    sentinel.write_text("old candidate", encoding="utf-8")
    with pytest.raises(ManagedUpdateFailure) as raised:
        backend.prepare(request)
    assert raised.value.code is FailureCode.PREPARE_FAILED
    assert sentinel.read_text(encoding="utf-8") == "old candidate"
    assert builder.requests == []


def test_prepare_uses_verified_staging_even_if_download_is_replaced(tmp_path: Path):
    backend, layout, _, _, request = _fixture(tmp_path)
    backend.verify(request)
    request.bundle_path.write_bytes(b"replaced after verification")
    candidate = backend.prepare(request)
    assert candidate.entrypoint == layout.version_root("2.0") / "payload" / "main.py"
    assert candidate.entrypoint.read_text(encoding="utf-8") == "print('managed')\n"


def test_prepare_rejects_candidate_builder_evidence_outside_exact_launch_path(tmp_path: Path):
    builder = Builder(wrong_evidence=True)
    backend, _, _, _, request = _fixture(tmp_path, builder=builder)
    backend.verify(request)
    with pytest.raises(ManagedUpdateFailure) as raised:
        backend.prepare(request)
    assert raised.value.code is FailureCode.PREPARE_FAILED


def test_rollback_restores_pointer_without_deleting_either_launchable_version(tmp_path: Path):
    backend, layout, _, _, request = _fixture(tmp_path)
    backend.verify(request)
    candidate = backend.prepare(request)
    receipt = backend.commit(candidate)
    backend.rollback(receipt)
    assert layout.events == ["eligible", "commit", "rollback"]
    assert receipt.previous_root.is_dir()
    assert receipt.candidate_root.is_dir()
