from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

from ClipAI.core.update_catalog import ManagedUpdateCatalog, ManagedUpdateRelease


CATALOG_KIND = "clipai-managed-update-v1"
_CATALOG_FIELDS = {"schema_version", "catalog_kind", "channel", "generated_at", "releases"}
_RELEASE_FIELDS = {
    "version",
    "bundle_url",
    "bundle_sha256",
    "bundle_size",
    "manifest_sha256",
    "key_id",
    "minimum_launcher_version",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CatalogValidationError(ValueError):
    pass


def parse_catalog(content: bytes, *, expected_channel: str = "stable") -> ManagedUpdateCatalog:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError("catalog is not valid UTF-8 JSON") from exc
    data = _exact_mapping(payload, _CATALOG_FIELDS, "catalog")
    if data["schema_version"] != 1 or data["catalog_kind"] != CATALOG_KIND:
        raise CatalogValidationError("catalog identity is unsupported")
    channel = _text(data["channel"], "catalog.channel")
    if channel != expected_channel:
        raise CatalogValidationError("catalog channel does not match")
    generated_at = _timestamp(data["generated_at"])
    raw_releases = data["releases"]
    if not isinstance(raw_releases, list):
        raise CatalogValidationError("catalog.releases must be a list")
    releases = tuple(_release(item, channel) for item in raw_releases)
    versions = [release.version for release in releases]
    if len(versions) != len(set(versions)):
        raise CatalogValidationError("catalog contains duplicate versions")
    return ManagedUpdateCatalog(channel, generated_at, releases)


def select_update(
    catalog: ManagedUpdateCatalog,
    *,
    installed_version: str,
    launcher_version: str,
) -> ManagedUpdateRelease | None:
    installed = _version(installed_version, "installed_version")
    launcher = _version(launcher_version, "launcher_version")
    eligible = [
        release
        for release in catalog.releases
        if Version(release.version) > installed
        and Version(release.minimum_launcher_version) <= launcher
    ]
    return max(eligible, key=lambda release: Version(release.version), default=None)


def _release(value: object, channel: str) -> ManagedUpdateRelease:
    data = _exact_mapping(value, _RELEASE_FIELDS, "release")
    version = _version_text(data["version"], "release.version")
    parsed = Version(version)
    if channel == "stable" and parsed.is_prerelease:
        raise CatalogValidationError("stable catalog contains a prerelease")
    url = _text(data["bundle_url"], "release.bundle_url")
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username:
        raise CatalogValidationError("release.bundle_url must be HTTPS")
    size = data["bundle_size"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise CatalogValidationError("release.bundle_size must be positive")
    bundle_hash = _hash(data["bundle_sha256"], "release.bundle_sha256")
    manifest_hash = _hash(data["manifest_sha256"], "release.manifest_sha256")
    key_id = _text(data["key_id"], "release.key_id")
    if _KEY_ID.fullmatch(key_id) is None:
        raise CatalogValidationError("release.key_id is invalid")
    minimum_launcher = _version_text(
        data["minimum_launcher_version"], "release.minimum_launcher_version"
    )
    return ManagedUpdateRelease(
        version,
        url,
        bundle_hash,
        size,
        manifest_hash,
        key_id,
        minimum_launcher,
    )


def _exact_mapping(value: object, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CatalogValidationError(f"{path} fields do not match schema")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CatalogValidationError(f"{path} must be a non-empty canonical string")
    return value


def _version_text(value: object, path: str) -> str:
    text = _text(value, path)
    parsed = _version(text, path)
    if str(parsed) != text:
        raise CatalogValidationError(f"{path} must be normalized")
    return text


def _version(value: str, path: str) -> Version:
    try:
        return Version(value)
    except InvalidVersion as exc:
        raise CatalogValidationError(f"{path} is not a PEP 440 version") from exc


def _hash(value: object, path: str) -> str:
    text = _text(value, path)
    if _SHA256.fullmatch(text) is None:
        raise CatalogValidationError(f"{path} must be lowercase SHA-256")
    return text


def _timestamp(value: object) -> str:
    text = _text(value, "catalog.generated_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogValidationError("catalog.generated_at must be RFC 3339") from exc
    if parsed.tzinfo is None:
        raise CatalogValidationError("catalog.generated_at must include timezone")
    return text
