from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedUpdateRelease:
    version: str
    bundle_url: str
    bundle_sha256: str
    bundle_size: int
    manifest_sha256: str
    key_id: str
    minimum_launcher_version: str


@dataclass(frozen=True)
class ManagedUpdateCatalog:
    channel: str
    generated_at: str
    releases: tuple[ManagedUpdateRelease, ...]
