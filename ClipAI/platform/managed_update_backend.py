from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath

from packaging.version import Version

from ClipAI.core.managed_update import CommitReceipt, FailureCode, ManagedUpdateFailure, TransactionId
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_bundle import InstallManifest
from ClipAI.core.update_ports import CandidateBuildRequest, CandidateEnvironment, CandidateEnvironmentBuilder
from ClipAI.platform.managed_install import DocumentVerifier, ManagedInstallLayout
from ClipAI.platform.managed_update_fs import (
    ManagedUpdateFileError,
    atomic_write_json,
    copy_regular_tree,
    extract_prefixed_zip,
    file_sha256,
    native_path,
    read_json,
    remove_tree,
    require_contained,
    unlink_file,
)
from ClipAI.platform.update_bundle import BundleValidationError, parse_install_manifest, verify_bundle_inventory
from ClipAI.platform.update_catalog import MAX_BUNDLE_SIZE


@dataclass(frozen=True)
class _VerifiedBundle:
    request: UpdateRequestArtifact
    staging_root: Path
    manifest: InstallManifest


class FilesystemManagedUpdateBackend:
    """Admit one verified bundle, prepare its inactive version, and switch the pointer."""

    def __init__(
        self,
        *,
        layout: ManagedInstallLayout,
        manifest_verifier: DocumentVerifier,
        candidate_builder: CandidateEnvironmentBuilder,
        base_python: str | Path,
    ) -> None:
        self._layout = layout
        self._manifest_verifier = manifest_verifier
        self._candidate_builder = candidate_builder
        self._base_python = Path(base_python).resolve()
        self._verified: dict[TransactionId, _VerifiedBundle] = {}
        self._candidate_transactions: dict[str, TransactionId] = {}

    def verify(self, request: UpdateRequestArtifact) -> None:
        self._layout.assert_update_eligible(request)
        if Version(request.target_version) <= Version(request.installed_version):
            raise ManagedUpdateFailure(FailureCode.BUNDLE_INVALID, "target version is not newer")
        if request.bundle_size > MAX_BUNDLE_SIZE:
            raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle exceeds supported size")
        transaction_root = self._transaction_root(request)
        try:
            bundle = require_contained(transaction_root, request.bundle_path)
            stat = native_path(bundle).stat()
            if stat.st_size != request.bundle_size or file_sha256(bundle) != request.bundle_sha256:
                raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "downloaded bundle identity does not match catalog")
        except ManagedUpdateFailure:
            raise
        except (OSError, ManagedUpdateFileError) as exc:
            raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "downloaded bundle is unavailable") from exc

        staging = transaction_root / "verified-bundle"
        remove_tree(staging)
        try:
            extract_prefixed_zip(
                bundle,
                staging,
                maximum_uncompressed_size=min(2 * 1024 * 1024 * 1024, max(64 * 1024 * 1024, request.bundle_size * 50)),
            )
            manifest_path = staging / "install-manifest.json"
            if file_sha256(manifest_path) != request.manifest_sha256:
                raise ManagedUpdateFailure(FailureCode.SIGNATURE_INVALID, "manifest identity does not match catalog")
            try:
                self._manifest_verifier.verify(
                    manifest_path,
                    staging / "install-manifest.json.sig",
                    key_id=request.key_id,
                )
            except Exception as exc:
                raise ManagedUpdateFailure(FailureCode.SIGNATURE_INVALID, "manifest signature is invalid") from exc
            manifest = parse_install_manifest(read_json(manifest_path))
            if manifest.app_version != request.target_version or manifest.key_id != request.key_id:
                raise ManagedUpdateFailure(FailureCode.BUNDLE_INVALID, "bundle release identity does not match request")
            verify_bundle_inventory(staging, manifest)
        except ManagedUpdateFailure:
            self._discard(staging)
            raise
        except (OSError, ManagedUpdateFileError, BundleValidationError) as exc:
            self._discard(staging)
            raise ManagedUpdateFailure(FailureCode.BUNDLE_INVALID, "bundle structure or inventory is invalid") from exc
        self._verified[request.transaction_id] = _VerifiedBundle(request, staging, manifest)

    def prepare(self, request: UpdateRequestArtifact) -> CandidateEnvironment:
        verified = self._verified.get(request.transaction_id)
        if verified is None or verified.request != request:
            raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "transaction has no matching verified bundle")
        target_root = self._layout.version_root(request.target_version)
        owner_path = target_root.parent / f".{target_root.name}.candidate-owner.json"
        try:
            self._reserve_target(target_root, owner_path, request)
            copy_regular_tree(verified.staging_root, target_root)
            verify_bundle_inventory(target_root, verified.manifest)
            candidate = self._candidate_builder.build(CandidateBuildRequest(
                transaction_id=request.transaction_id,
                candidate_root=target_root,
                base_python=self._base_python,
                expected_version=request.target_version,
                entrypoint=verified.manifest.entrypoint,
            ))
            self._validate_candidate(candidate, verified.manifest, target_root)
            unlink_file(owner_path)
            self._candidate_transactions[_path_key(target_root)] = request.transaction_id
            return candidate
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "offline candidate preparation failed") from exc

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

    def _validate_candidate(self, candidate: CandidateEnvironment, manifest: InstallManifest, target_root: Path) -> None:
        expected_python = target_root / ".venv" / "Scripts" / "python.exe"
        expected_entrypoint = target_root.joinpath(*PurePosixPath(manifest.entrypoint).parts)
        if (
            _path_key(candidate.root) != _path_key(target_root)
            or candidate.version != manifest.app_version
            or _path_key(candidate.python) != _path_key(expected_python)
            or _path_key(candidate.entrypoint) != _path_key(expected_entrypoint)
            or not native_path(expected_python).is_file()
            or not native_path(expected_entrypoint).is_file()
        ):
            raise ManagedUpdateFailure(FailureCode.PREPARE_FAILED, "candidate builder returned mismatched launch evidence")

    def _cleanup_for(self, candidate_root: Path) -> None:
        transaction_id = self._candidate_transactions.pop(_path_key(candidate_root), None)
        if transaction_id is None:
            return
        verified = self._verified.pop(transaction_id, None)
        if verified is not None:
            self._discard(verified.staging_root)

    @staticmethod
    def _discard(path: Path) -> None:
        try:
            remove_tree(path)
        except ManagedUpdateFileError:
            pass


def _path_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))
