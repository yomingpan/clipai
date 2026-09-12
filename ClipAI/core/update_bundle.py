from __future__ import annotations

from dataclasses import dataclass


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
