from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.first_install import InstallAdmission
from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.core.update_bundle import BundleAdmissionRequest
from ClipAI.core.update_ports import (
    CandidateEnvironment,
    CandidateEnvironmentBuilder,
    ManagedUpdateGate,
)
from ClipAI.platform.managed_install import DocumentVerifier, MARKER_KIND, STATE_KIND
from ClipAI.platform.managed_update_fs import (
    ManagedUpdateFileError,
    atomic_write_json,
    canonical_path,
    copy_file_atomically,
    native_path,
    remove_tree,
    require_contained,
    unlink_file,
)
from ClipAI.platform.managed_update_mutex import WindowsManagedUpdateGate, admit_installation
from ClipAI.platform.update_catalog import MAX_BUNDLE_SIZE
from ClipAI.platform.prepared_managed_payload import PreparedManagedPayloadMaterializer
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
        self._materializer = PreparedManagedPayloadMaterializer(candidate_builder=candidate_builder)
        self._trusted_keyring_path = canonical_path(trusted_keyring_path)
        self._update_gate_factory = update_gate_factory

    def install(self, command: InstallManagedCommand) -> CandidateEnvironment:
        admission = admit_installation(command.install_root, self._update_gate_factory)
        work = None
        try:
            work = self.open_install(command, admission)
            work.prepare()
            return work.commit()
        except ManagedUpdateFailure:
            if work is not None:
                work.cleanup()
            raise
        except Exception as exc:
            if work is not None:
                work.cleanup()
            code = FailureCode.DOWNLOAD_FAILED if isinstance(exc, ManagedUpdateFileError) else FailureCode.PREPARE_FAILED
            raise ManagedUpdateFailure(code, "managed initial installation failed") from exc
        finally:
            admission.close()

    def open_install(self, command: InstallManagedCommand, admission: InstallAdmission) -> _InitialInstallWork:
        admission.require_active(command.install_root)
        install_root = canonical_path(command.install_root)
        shared_root = canonical_path(command.shared_root)
        if (install_root == shared_root or install_root.is_relative_to(shared_root)
                or shared_root.is_relative_to(install_root)):
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "install and shared roots overlap")
        target = require_contained(install_root / "versions", install_root / "versions" / command.expected_version)
        if target == install_root / "versions":
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "version root is invalid")
        targets = (install_root / "install-state.json", install_root / "managed-install.json",
                   target, install_root / "launcher")
        # This check happens after admission, including for the existing CLI.
        if any(native_path(path).exists() for path in targets):
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "managed install target already exists")
        return _InitialInstallWork(self, command, admission)

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


class _InitialInstallWork:
    """The existing engine's prepare/commit work, bound to one live admission."""

    def __init__(self, installer: FilesystemManagedInstaller, command: InstallManagedCommand,
                 admission: InstallAdmission) -> None:
        self._installer, self._command, self._admission = installer, command, admission
        self._candidate: CandidateEnvironment | None = None
        self._started = False
        self._prepared = False
        self._committed = False

    def prepare(self) -> None:
        command = self._command
        self._admission.require_active(command.install_root)
        if self._started:
            raise RuntimeError("initial installation preparation already started")
        self._started = True
        transaction_root = require_contained(command.shared_root,
            command.shared_root / "managed-update" / "transactions" / str(command.transaction_id))
        admitted_bundle = transaction_root / "install-bundle.zip"
        copy_file_atomically(command.bundle_path, admitted_bundle,
                            maximum_size=min(command.bundle_size, MAX_BUNDLE_SIZE))
        verified = self._installer._stager.stage(BundleAdmissionRequest(
            transaction_root=transaction_root, bundle_path=admitted_bundle,
            bundle_size=command.bundle_size, bundle_sha256=command.bundle_sha256,
            manifest_sha256=command.manifest_sha256, expected_version=command.expected_version,
            key_id=command.key_id,
        ))
        target = require_contained(command.install_root / "versions",
                                   command.install_root / "versions" / command.expected_version)
        self._candidate = self._installer._materializer.prepare(
            verified, target_root=target, transaction_id=command.transaction_id,
            base_python=command.base_python)
        launcher = require_contained(command.install_root, command.install_root / "launcher")
        self._installer._materializer.prepare(
            verified, target_root=launcher, transaction_id=command.transaction_id,
            base_python=command.base_python)
        copy_file_atomically(self._installer._trusted_keyring_path,
                            launcher / "managed-update-trusted-keys.json", maximum_size=1024 * 1024)
        self._prepared = True

    def commit(self) -> CandidateEnvironment:
        command = self._command
        self._admission.require_active(command.install_root)
        if not self._prepared or self._candidate is None or self._committed:
            raise RuntimeError("initial installation is not prepared or already committed")
        atomic_write_json(command.install_root / "install-state.json", {
            "schema_version": 1, "state_kind": STATE_KIND,
            "managed_install_id": command.managed_install_id, "revision": 0,
            "current_version": command.expected_version, "previous_version": None,
        })
        atomic_write_json(command.install_root / "managed-install.json", {
            "schema_version": 1, "marker_kind": MARKER_KIND,
            "managed_install_id": command.managed_install_id,
            "install_root": str(command.install_root), "shared_root": str(command.shared_root),
            "launcher_version": command.launcher_version, "key_id": command.key_id,
        })
        self._committed = True
        return self._candidate

    def cleanup(self) -> None:
        command = self._command
        self._admission.require_active(command.install_root)
        if self._started:
            self._installer._cleanup_failed_install(
                command.install_root / "versions" / command.expected_version,
                command.install_root / "launcher", command.install_root / "install-state.json",
                command.install_root / "managed-install.json")
