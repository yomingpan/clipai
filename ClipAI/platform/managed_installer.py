from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.core.update_bundle import BundleAdmissionRequest
from ClipAI.core.update_ports import (
    CandidateBuildRequest,
    CandidateEnvironment,
    CandidateEnvironmentBuilder,
    ManagedUpdateGate,
)
from ClipAI.platform.candidate_environment import validate_candidate_environment
from ClipAI.platform.managed_install import DocumentVerifier, MARKER_KIND, STATE_KIND
from ClipAI.platform.managed_update_fs import (
    ManagedUpdateFileError,
    atomic_write_json,
    canonical_path,
    copy_file_atomically,
    copy_regular_tree,
    native_path,
    remove_tree,
    require_contained,
    unlink_file,
)
from ClipAI.platform.managed_update_mutex import WindowsManagedUpdateGate
from ClipAI.platform.update_bundle import verify_bundle_inventory
from ClipAI.platform.update_catalog import MAX_BUNDLE_SIZE
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager


class FilesystemManagedInstaller:
    """Build an initial managed version before publishing local eligibility."""

    def __init__(
        self,
        *,
        manifest_verifier: DocumentVerifier,
        candidate_builder: CandidateEnvironmentBuilder,
        trusted_keyring_path: str | Path,
        update_gate_factory: Callable[[Path], ManagedUpdateGate] = WindowsManagedUpdateGate,
    ) -> None:
        self._stager = VerifiedManagedBundleStager(manifest_verifier=manifest_verifier)
        self._candidate_builder = candidate_builder
        self._trusted_keyring_path = canonical_path(trusted_keyring_path)
        self._update_gate_factory = update_gate_factory

    def install(self, command: InstallManagedCommand) -> CandidateEnvironment:
        install_root = canonical_path(command.install_root)
        shared_root = canonical_path(command.shared_root)
        if (
            install_root == shared_root
            or install_root.is_relative_to(shared_root)
            or shared_root.is_relative_to(install_root)
        ):
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "install and shared roots overlap")

        state_path = install_root / "install-state.json"
        marker_path = install_root / "managed-install.json"
        target_root = require_contained(
            install_root / "versions",
            install_root / "versions" / command.expected_version,
        )
        launcher_root = require_contained(install_root, install_root / "launcher")
        if any(native_path(path).exists() for path in (state_path, marker_path, target_root, launcher_root)):
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "managed install target already exists")

        lease = self._update_gate_factory(install_root).acquire()
        if lease is None:
            raise ManagedUpdateFailure(FailureCode.UPDATE_BUSY, "managed install is busy")
        transaction_root = require_contained(
            shared_root,
            shared_root / "managed-update" / "transactions" / str(command.transaction_id),
        )
        admitted_bundle = transaction_root / "install-bundle.zip"
        try:
            copy_file_atomically(
                command.bundle_path,
                admitted_bundle,
                maximum_size=min(command.bundle_size, MAX_BUNDLE_SIZE),
            )
            verified = self._stager.stage(BundleAdmissionRequest(
                transaction_root=transaction_root,
                bundle_path=admitted_bundle,
                bundle_size=command.bundle_size,
                bundle_sha256=command.bundle_sha256,
                manifest_sha256=command.manifest_sha256,
                expected_version=command.expected_version,
                key_id=command.key_id,
            ))
            copy_regular_tree(verified.staging_root, target_root)
            verify_bundle_inventory(target_root, verified.manifest)
            build_request = CandidateBuildRequest(
                transaction_id=command.transaction_id,
                candidate_root=target_root,
                base_python=command.base_python,
                expected_version=command.expected_version,
                entrypoint=verified.manifest.entrypoint,
            )
            candidate = self._candidate_builder.build(build_request)
            validate_candidate_environment(candidate, build_request)
            copy_regular_tree(verified.staging_root, launcher_root)
            launcher_request = CandidateBuildRequest(
                transaction_id=command.transaction_id,
                candidate_root=launcher_root,
                base_python=command.base_python,
                expected_version=command.expected_version,
                entrypoint=verified.manifest.entrypoint,
            )
            launcher = self._candidate_builder.build(launcher_request)
            validate_candidate_environment(launcher, launcher_request)
            copy_file_atomically(
                self._trusted_keyring_path,
                launcher_root / "managed-update-trusted-keys.json",
                maximum_size=1024 * 1024,
            )
            atomic_write_json(state_path, {
                "schema_version": 1,
                "state_kind": STATE_KIND,
                "managed_install_id": command.managed_install_id,
                "revision": 0,
                "current_version": command.expected_version,
                "previous_version": None,
            })
            atomic_write_json(marker_path, {
                "schema_version": 1,
                "marker_kind": MARKER_KIND,
                "managed_install_id": command.managed_install_id,
                "install_root": str(install_root),
                "shared_root": str(shared_root),
                "launcher_version": command.launcher_version,
                "key_id": command.key_id,
            })
            return candidate
        except ManagedUpdateFailure:
            self._cleanup_failed_install(target_root, launcher_root, state_path, marker_path)
            raise
        except Exception as exc:
            self._cleanup_failed_install(target_root, launcher_root, state_path, marker_path)
            code = FailureCode.DOWNLOAD_FAILED if isinstance(exc, ManagedUpdateFileError) else FailureCode.PREPARE_FAILED
            raise ManagedUpdateFailure(code, "managed initial installation failed") from exc
        finally:
            lease.close()

    @staticmethod
    def _cleanup_failed_install(
        target_root: Path,
        launcher_root: Path,
        state_path: Path,
        marker_path: Path,
    ) -> None:
        if native_path(marker_path).exists():
            return
        for cleanup in (
            lambda: unlink_file(state_path),
            lambda: remove_tree(target_root),
            lambda: remove_tree(launcher_root),
        ):
            try:
                cleanup()
            except ManagedUpdateFileError:
                # Preserve the original installation failure. A future retry still
                # refuses any surviving partial state instead of overwriting it.
                pass
