from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from packaging.version import Version

from ClipAI.core.managed_update import CommitReceipt, FailureCode, ManagedUpdateFailure, TransactionId
from ClipAI.core.update_artifacts import HandoffReadyArtifact, UpdateRequestArtifact
from ClipAI.core.update_bundle import BundleAdmissionRequest, VerifiedManagedBundle
from ClipAI.core.update_ports import CandidateBuildRequest, CandidateEnvironment, CandidateEnvironmentBuilder
from ClipAI.platform.managed_install import DocumentVerifier, ManagedInstallLayout
from ClipAI.platform.candidate_environment import validate_candidate_environment
from ClipAI.platform.managed_update_fs import (
    ManagedUpdateFileError,
    atomic_write_json,
    copy_regular_tree,
    native_path,
    read_json,
    remove_tree,
    require_contained,
    unlink_file,
)
from ClipAI.platform.update_bundle import verify_bundle_inventory
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager


class FilesystemManagedUpdateBackend:
    """Admit one verified bundle, prepare its inactive version, and switch the pointer."""

    def __init__(
        self,
        *,
        layout: ManagedInstallLayout,
        manifest_verifier: DocumentVerifier,
        candidate_builder: CandidateEnvironmentBuilder,
        base_python: str | Path,
        now: Callable[[], str],
    ) -> None:
        self._layout = layout
        self._candidate_builder = candidate_builder
        self._base_python = Path(base_python).resolve()
        self._now = now
        self._bundle_stager = VerifiedManagedBundleStager(manifest_verifier=manifest_verifier)
        self._verified: dict[TransactionId, tuple[UpdateRequestArtifact, VerifiedManagedBundle]] = {}
        self._candidate_transactions: dict[str, TransactionId] = {}

    def verify(self, request: UpdateRequestArtifact) -> None:
        self._layout.assert_update_eligible(request)
        if Version(request.target_version) <= Version(request.installed_version):
            raise ManagedUpdateFailure(FailureCode.BUNDLE_INVALID, "target version is not newer")
        transaction_root = self._transaction_root(request)
        verified = self._bundle_stager.stage(BundleAdmissionRequest(
            transaction_root=transaction_root,
            bundle_path=request.bundle_path,
            bundle_size=request.bundle_size,
            bundle_sha256=request.bundle_sha256,
            manifest_sha256=request.manifest_sha256,
            expected_version=request.target_version,
            key_id=request.key_id,
        ))
        self._verified[request.transaction_id] = (request, verified)

    def prepare(self, request: UpdateRequestArtifact) -> CandidateEnvironment:
        admitted = self._verified.get(request.transaction_id)
        if admitted is None or admitted[0] != request:
            raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "transaction has no matching verified bundle")
        verified = admitted[1]
        target_root = self._layout.version_root(request.target_version)
        owner_path = target_root.parent / f".{target_root.name}.candidate-owner.json"
        try:
            self._reserve_target(target_root, owner_path, request)
            copy_regular_tree(verified.staging_root, target_root)
            verify_bundle_inventory(target_root, verified.manifest)
            build_request = CandidateBuildRequest(
                transaction_id=request.transaction_id,
                candidate_root=target_root,
                base_python=self._base_python,
                expected_version=request.target_version,
                entrypoint=verified.manifest.entrypoint,
            )
            candidate = self._candidate_builder.build(build_request)
            validate_candidate_environment(candidate, build_request)
            unlink_file(owner_path)
            ManagedUpdateArtifactStore(
                shared_root=request.shared_root,
                transaction_id=str(request.transaction_id),
            ).write(HandoffReadyArtifact(
                request.transaction_id,
                self._now(),
                candidate.root,
                candidate.python,
                request.manifest_sha256,
                request.target_version,
            ))
            self._candidate_transactions[_path_key(target_root)] = request.transaction_id
            return candidate
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "offline candidate preparation failed") from exc

    def known_good_root(self, request: UpdateRequestArtifact) -> Path:
        return self._layout.version_root(request.installed_version)

    def commit(self, candidate: CandidateEnvironment) -> CommitReceipt:
        if _path_key(candidate.root) not in self._candidate_transactions:
            raise ManagedUpdateFailure(FailureCode.COMMIT_FAILED, "candidate is not owned by a prepared transaction")
        return self._layout.commit(candidate)

    def rollback(self, receipt: CommitReceipt) -> None:
        self._layout.rollback(receipt)
        self._cleanup_for(receipt.candidate_root)

    def finalize(self, receipt: CommitReceipt) -> None:
        self._layout.finalize(receipt)
        self._cleanup_for(receipt.candidate_root)

    def _transaction_root(self, request: UpdateRequestArtifact) -> Path:
        expected_shared = self._layout.shared_root
        if _path_key(request.shared_root) != _path_key(expected_shared):
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "request shared root does not match backend")
        return require_contained(
            expected_shared,
            expected_shared / "managed-update" / "transactions" / str(request.transaction_id),
        )

    def _reserve_target(self, target_root: Path, owner_path: Path, request: UpdateRequestArtifact) -> None:
        if native_path(target_root).exists():
            try:
                owner = read_json(owner_path)
            except Exception as exc:
                raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "target version root already exists") from exc
            expected = {
                "schema_version": 1,
                "transaction_id": str(request.transaction_id),
                "target_version": request.target_version,
            }
            if owner != expected:
                raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "target version root belongs to another transaction")
            remove_tree(target_root)
        elif native_path(owner_path).exists():
            owner = read_json(owner_path)
            if owner != {
                "schema_version": 1,
                "transaction_id": str(request.transaction_id),
                "target_version": request.target_version,
            }:
                raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "target reservation belongs to another transaction")
        atomic_write_json(owner_path, {
            "schema_version": 1,
            "transaction_id": str(request.transaction_id),
            "target_version": request.target_version,
        })

    def _cleanup_for(self, candidate_root: Path) -> None:
        transaction_id = self._candidate_transactions.pop(_path_key(candidate_root), None)
        if transaction_id is None:
            return
        verified = self._verified.pop(transaction_id, None)
        if verified is not None:
            self._discard(verified[1].staging_root)

    @staticmethod
    def _discard(path: Path) -> None:
        try:
            remove_tree(path)
        except ManagedUpdateFileError:
            pass


def _path_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))
