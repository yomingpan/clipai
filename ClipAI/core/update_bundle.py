from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManifestFile:
    path: str
    size: int
    sha256: str
    role: str


@dataclass(frozen=True)
class InstallManifest:
    app_version: str
    bundle_format: str
    entrypoint: str
    python_requires: str
    requirements_lock_sha256: str
    files: tuple[ManifestFile, ...]
    signing_namespace: str
    key_id: str


@dataclass(frozen=True)
class BundleAdmissionRequest:
    transaction_root: Path
    bundle_path: Path
    bundle_size: int
    bundle_sha256: str
    manifest_sha256: str
    expected_version: str
    key_id: str


@dataclass(frozen=True)
class VerifiedManagedBundle:
    staging_root: Path
    manifest: InstallManifest
