from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import TransactionId
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_ports import ManagedReleaseSource


class ManagedUpdateCoordinator:
    """Coordinate release discovery and download into one handoff request."""

    def __init__(
        self,
        *,
        release_source: ManagedReleaseSource,
        now: Callable[[], str],
    ) -> None:
        self._release_source = release_source
        self._now = now

    def prepare(
        self,
        identity: ManagedUpdateClientIdentity,
        transaction_id: TransactionId,
    ) -> UpdateRequestArtifact | None:
        release = self._release_source.discover(
            installed_version=identity.installed_version,
            launcher_version=identity.launcher_version,
        )
        if release is None:
            return None
        bundle_path = self._release_source.download(
            release,
            shared_root=identity.shared_root,
            transaction_id=transaction_id,
        )
        return UpdateRequestArtifact(
            transaction_id=transaction_id,
            created_at=self._now(),
            installed_version=identity.installed_version,
            target_version=release.version,
            installed_executable=identity.installed_executable,
            installed_process_id=identity.installed_process_id,
            bundle_path=bundle_path,
            bundle_size=release.bundle_size,
            bundle_sha256=release.bundle_sha256,
            manifest_sha256=release.manifest_sha256,
            key_id=release.key_id,
            install_root=identity.install_root,
            shared_root=identity.shared_root,
            managed_install_id=identity.managed_install_id,
        )
