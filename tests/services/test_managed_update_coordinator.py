from pathlib import Path

from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import transaction_id
from ClipAI.core.update_catalog import ManagedUpdateRelease
from ClipAI.services.managed_update_coordinator import ManagedUpdateCoordinator


NOW = "2026-09-13T00:00:00+00:00"


class _ReleaseSource:
    def __init__(self, release: ManagedUpdateRelease | None, bundle_path: Path) -> None:
        self.release = release
        self.bundle_path = bundle_path
        self.downloads = []

    def discover(self, *, installed_version: str, launcher_version: str):
        assert (installed_version, launcher_version) == ("1.0", "1.0")
        return self.release

    def download(self, release, *, shared_root, transaction_id):
        self.downloads.append((release, shared_root, transaction_id))
        return self.bundle_path


def _identity(tmp_path: Path) -> ManagedUpdateClientIdentity:
    return ManagedUpdateClientIdentity(
        installed_version="1.0",
        launcher_version="1.0",
        installed_executable=(tmp_path / "install" / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe").resolve(),
        installed_process_id=321,
        install_root=(tmp_path / "install").resolve(),
        shared_root=(tmp_path / "shared").resolve(),
        managed_install_id="managed-1",
    )


def test_coordinator_discovers_downloads_and_builds_one_exact_update_request(tmp_path: Path):
    release = ManagedUpdateRelease(
        version="2.0",
        bundle_url="https://updates.example/clipai.zip",
        bundle_sha256="a" * 64,
        bundle_size=42,
        manifest_sha256="b" * 64,
        key_id="release-key",
        minimum_launcher_version="1.0",
    )
    bundle_path = (tmp_path / "shared" / "managed-update" / "transactions" / "tx-1" / "download" / "bundle.zip").resolve()
    source = _ReleaseSource(release, bundle_path)
    coordinator = ManagedUpdateCoordinator(release_source=source, now=lambda: NOW)

    request = coordinator.prepare(_identity(tmp_path), transaction_id("tx-1"))

    assert request is not None
    assert request.transaction_id == "tx-1"
    assert request.created_at == NOW
    assert (request.installed_version, request.target_version) == ("1.0", "2.0")
    assert request.installed_process_id == 321
    assert request.bundle_path == bundle_path
    assert (request.bundle_size, request.bundle_sha256, request.manifest_sha256) == (42, "a" * 64, "b" * 64)
    assert (request.key_id, request.managed_install_id) == ("release-key", "managed-1")
    assert source.downloads == [(release, _identity(tmp_path).shared_root, transaction_id("tx-1"))]


def test_coordinator_does_not_download_when_no_update_is_available(tmp_path: Path):
    source = _ReleaseSource(None, tmp_path / "unused.zip")
    coordinator = ManagedUpdateCoordinator(release_source=source, now=lambda: NOW)

    assert coordinator.prepare(_identity(tmp_path), transaction_id("tx-none")) is None
    assert source.downloads == []
