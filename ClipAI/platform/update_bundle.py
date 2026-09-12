from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from ClipAI.core.update_bundle import InstallManifest, ManifestFile
from ClipAI.platform.update_signature import SIGNING_NAMESPACE


BUNDLE_FORMAT = "clipai-managed-v1"
_FIELDS = {"schema_version", "app_version", "bundle_format", "entrypoint", "python_requires", "requirements_lock_sha256", "files", "signing_namespace", "key_id"}
_FILE_FIELDS = {"path", "size", "sha256", "role"}
_ROLES = {"payload", "wheel", "metadata"}
_DENIED = {".env", ".git", ".venv", "data", "logs", "diagnostics", "launcher", "updater", "update-journal.json"}
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class BundleValidationError(ValueError):
    pass


def parse_install_manifest(payload: object) -> InstallManifest:
    data = _mapping(payload, _FIELDS, "manifest")
    if data["schema_version"] != 1 or data["bundle_format"] != BUNDLE_FORMAT:
        raise BundleValidationError("bundle identity is unsupported")
    version = _version(data["app_version"])
    entrypoint = _relative(data["entrypoint"])
    python_requires = _text(data["python_requires"], "python_requires")
    try:
        SpecifierSet(python_requires)
    except InvalidSpecifier as exc:
        raise BundleValidationError("python_requires is invalid") from exc
    lock_hash = _sha256(data["requirements_lock_sha256"])
    if data["signing_namespace"] != SIGNING_NAMESPACE:
        raise BundleValidationError("signing namespace is unsupported")
    key_id = _text(data["key_id"], "key_id")
    if _KEY_ID.fullmatch(key_id) is None:
        raise BundleValidationError("key_id is invalid")
    raw_files = data["files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise BundleValidationError("files must be a non-empty list")
    files = tuple(_file(item) for item in raw_files)
    paths = [item.path for item in files]
    if len(paths) != len(set(paths)):
        raise BundleValidationError("manifest contains duplicate paths")
    inventory = {item.path: item for item in files}
    if entrypoint not in inventory or inventory[entrypoint].role != "payload":
        raise BundleValidationError("entrypoint must name a payload file")
    lock = inventory.get("requirements.lock")
    if lock is None or lock.role != "metadata" or lock.sha256 != lock_hash:
        raise BundleValidationError("requirements.lock identity does not match")
    if not any(item.role == "wheel" and item.path.startswith("wheelhouse/") for item in files):
        raise BundleValidationError("wheelhouse must contain an offline wheel")
    return InstallManifest(version, BUNDLE_FORMAT, entrypoint, python_requires, lock_hash, files, SIGNING_NAMESPACE, key_id)


def _file(value: object) -> ManifestFile:
    data = _mapping(value, _FILE_FIELDS, "file")
    path = _relative(data["path"])
    first = PurePosixPath(path).parts[0].casefold()
    if first in _DENIED or PurePosixPath(path).name.casefold() in _DENIED:
        raise BundleValidationError("manifest contains user-owned or host file")
    size = data["size"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise BundleValidationError("file size is invalid")
    role = data["role"]
    if role not in _ROLES:
        raise BundleValidationError("file role is invalid")
    if role == "wheel" and not path.startswith("wheelhouse/"):
        raise BundleValidationError("wheel role must remain in wheelhouse")
    return ManifestFile(path, size, _sha256(data["sha256"]), role)


def _mapping(value: object, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise BundleValidationError(f"{name} fields do not match schema")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BundleValidationError(f"{name} must be a canonical string")
    return value


def _relative(value: object) -> str:
    text = _text(value, "path")
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        raise BundleValidationError("path is not normalized")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {".", "..", ""} for part in path.parts) or path.as_posix() != text:
        raise BundleValidationError("path is not a contained relative path")
    return text


def _version(value: object) -> str:
    text = _text(value, "app_version")
    try:
        parsed = Version(text)
    except InvalidVersion as exc:
        raise BundleValidationError("app_version is invalid") from exc
    if str(parsed) != text:
        raise BundleValidationError("app_version is not normalized")
    return text


def _sha256(value: object) -> str:
    text = _text(value, "sha256")
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise BundleValidationError("sha256 is invalid")
    return text
