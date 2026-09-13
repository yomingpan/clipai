from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, TransactionId
from ClipAI.core.update_catalog import ManagedUpdateRelease
from ClipAI.platform.managed_update_fs import canonical_path, require_contained
from ClipAI.platform.update_catalog import CatalogValidationError, parse_catalog, select_update


class ManagedUpdateTransport(Protocol):
    def fetch_catalog(self, url: str) -> bytes: ...

    def download_bundle(
        self,
        url: str,
        destination: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> Path: ...


class HttpsManagedReleaseSource:
    """Own catalog admission, release selection, and transaction download paths."""

    def __init__(
        self,
        *,
        catalog_url: str,
        transport: ManagedUpdateTransport,
        channel: str = "stable",
    ) -> None:
        self._catalog_url = catalog_url
        self._transport = transport
        self._channel = channel

    def discover(
        self,
        *,
        installed_version: str,
        launcher_version: str,
    ) -> ManagedUpdateRelease | None:
        content = self._transport.fetch_catalog(self._catalog_url)
        try:
            catalog = parse_catalog(content, expected_channel=self._channel)
            return select_update(
                catalog,
                installed_version=installed_version,
                launcher_version=launcher_version,
            )
        except CatalogValidationError as exc:
            raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "managed update catalog is invalid") from exc

    def download(
        self,
        release: ManagedUpdateRelease,
        *,
        shared_root: Path,
        transaction_id: TransactionId,
    ) -> Path:
        transaction_root = require_contained(
            shared_root,
            shared_root / "managed-update" / "transactions" / str(transaction_id),
        )
        destination = require_contained(
            transaction_root,
            transaction_root / "download" / "bundle.zip",
        )
        downloaded = self._transport.download_bundle(
            release.bundle_url,
            destination,
            expected_size=release.bundle_size,
            expected_sha256=release.bundle_sha256,
        )
        if canonical_path(downloaded) != canonical_path(destination):
            raise ManagedUpdateFailure(
                FailureCode.DOWNLOAD_FAILED,
                "managed update transport returned an unexpected bundle path",
            )
        return destination
