import json
from pathlib import Path

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.platform.managed_release_source import HttpsManagedReleaseSource


class _Transport:
    def __init__(self, catalog: bytes) -> None:
        self.catalog = catalog
        self.fetches = []
        self.downloads = []

    def fetch_catalog(self, url: str) -> bytes:
        self.fetches.append(url)
        return self.catalog

    def download_bundle(self, url, destination, *, expected_size, expected_sha256):
        self.downloads.append((url, destination, expected_size, expected_sha256))
        return destination.resolve()


def test_release_source_selects_newer_catalog_release_and_owns_transaction_destination(tmp_path: Path):
    catalog = json.dumps({
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": [{
            "version": "2.0",
            "bundle_url": "https://updates.example/clipai.zip",
            "bundle_sha256": "a" * 64,
            "bundle_size": 42,
            "manifest_sha256": "b" * 64,
            "key_id": "release-key",
            "minimum_launcher_version": "1.0",
        }],
    }).encode("utf-8")
    transport = _Transport(catalog)
    source = HttpsManagedReleaseSource(
        catalog_url="https://updates.example/catalog.json",
        transport=transport,
    )

    release = source.discover(installed_version="1.0", launcher_version="1.0")
    assert release is not None
    destination = source.download(
        release,
        shared_root=(tmp_path / "shared").resolve(),
        transaction_id=transaction_id("tx-1"),
    )

    expected = (tmp_path / "shared" / "managed-update" / "transactions" / "tx-1" / "download" / "bundle.zip").resolve()
    assert destination == expected
    assert transport.fetches == ["https://updates.example/catalog.json"]
    assert transport.downloads == [
        ("https://updates.example/clipai.zip", expected, 42, "a" * 64),
    ]


def test_release_source_rejects_transport_path_outside_transaction(tmp_path: Path):
    catalog = json.dumps({
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": [{
            "version": "2.0",
            "bundle_url": "https://updates.example/clipai.zip",
            "bundle_sha256": "a" * 64,
            "bundle_size": 42,
            "manifest_sha256": "b" * 64,
            "key_id": "release-key",
            "minimum_launcher_version": "1.0",
        }],
    }).encode("utf-8")
    transport = _Transport(catalog)
    transport.bundle_path = (tmp_path / "outside.zip").resolve()

    def misdirected_download(*_args, **_kwargs):
        return transport.bundle_path

    transport.download_bundle = misdirected_download
    source = HttpsManagedReleaseSource(
        catalog_url="https://updates.example/catalog.json",
        transport=transport,
    )
    release = source.discover(installed_version="1.0", launcher_version="1.0")
    assert release is not None

    with pytest.raises(ManagedUpdateFailure) as failure:
        source.download(
            release,
            shared_root=(tmp_path / "shared").resolve(),
            transaction_id=transaction_id("tx-1"),
        )

    assert failure.value.code is FailureCode.DOWNLOAD_FAILED
