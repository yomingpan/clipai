from __future__ import annotations

from pathlib import Path

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.update_bundle import BundleAdmissionRequest, VerifiedManagedBundle
from ClipAI.platform.managed_install import DocumentVerifier
from ClipAI.platform.managed_update_fs import (
    ManagedUpdateFileError,
    extract_prefixed_zip,
    file_sha256,
    native_path,
    read_json,
    remove_tree,
    require_contained,
)
from ClipAI.platform.update_bundle import (
    BundleValidationError,
    parse_install_manifest,
    verify_bundle_inventory,
)
from ClipAI.platform.update_catalog import MAX_BUNDLE_SIZE


class VerifiedManagedBundleStager:
    """Own catalog-bound archive admission and immutable verified staging."""

    def __init__(self, *, manifest_verifier: DocumentVerifier) -> None:
        self._manifest_verifier = manifest_verifier

    def stage(self, request: BundleAdmissionRequest) -> VerifiedManagedBundle:
        if request.bundle_size > MAX_BUNDLE_SIZE:
            raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle exceeds supported size")
        try:
            bundle = require_contained(request.transaction_root, request.bundle_path)
            stat = native_path(bundle).stat()
            if stat.st_size != request.bundle_size or file_sha256(bundle) != request.bundle_sha256:
                raise ManagedUpdateFailure(
                    FailureCode.DOWNLOAD_FAILED,
                    "downloaded bundle identity does not match catalog",
                )
        except ManagedUpdateFailure:
            raise
        except (OSError, ManagedUpdateFileError) as exc:
            raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "downloaded bundle is unavailable") from exc

        staging = request.transaction_root / "verified-bundle"
        remove_tree(staging)
        try:
            extract_prefixed_zip(
                bundle,
                staging,
                maximum_uncompressed_size=min(
                    2 * 1024 * 1024 * 1024,
                    max(64 * 1024 * 1024, request.bundle_size * 50),
                ),
            )
            manifest_path = staging / "install-manifest.json"
            if file_sha256(manifest_path) != request.manifest_sha256:
                raise ManagedUpdateFailure(
                    FailureCode.SIGNATURE_INVALID,
                    "manifest identity does not match catalog",
                )
            try:
                self._manifest_verifier.verify(
                    manifest_path,
                    staging / "install-manifest.json.sig",
                    key_id=request.key_id,
                )
            except Exception as exc:
                raise ManagedUpdateFailure(
                    FailureCode.SIGNATURE_INVALID,
                    "manifest signature is invalid",
                ) from exc
            manifest = parse_install_manifest(read_json(manifest_path))
            if manifest.app_version != request.expected_version or manifest.key_id != request.key_id:
                raise ManagedUpdateFailure(
                    FailureCode.BUNDLE_INVALID,
                    "bundle release identity does not match request",
                )
            verify_bundle_inventory(staging, manifest)
            return VerifiedManagedBundle(staging, manifest)
        except ManagedUpdateFailure:
            _discard(staging)
            raise
        except (OSError, ManagedUpdateFileError, BundleValidationError) as exc:
            _discard(staging)
            raise ManagedUpdateFailure(
                FailureCode.BUNDLE_INVALID,
                "bundle structure or inventory is invalid",
            ) from exc


def _discard(path: Path) -> None:
    try:
        remove_tree(path)
    except ManagedUpdateFileError:
        pass
