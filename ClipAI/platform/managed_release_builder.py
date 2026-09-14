from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import subprocess
import uuid
from typing import Protocol

from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

from ClipAI.core.update_signing import TEST_KEY_ID
from ClipAI.platform.managed_update_fs import (
    atomic_write_bytes,
    atomic_write_json,
    copy_file_atomically,
    file_sha256,
    native_path,
    read_bytes,
    regular_file_inventory,
    unlink_file,
    write_prefixed_zip,
)
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_catalog import CATALOG_KIND, parse_catalog
from ClipAI.platform.update_bundle import parse_install_manifest
from ClipAI.platform.update_signature import SIGNING_NAMESPACE, canonical_json_bytes


class ManifestSigner(Protocol):
    def sign(self, manifest: bytes) -> bytes: ...


@dataclass(frozen=True)
class ManagedReleaseResult:
    bundle_path: Path
    bundle_sha256: str
    bundle_size: int
    manifest_sha256: str


@dataclass(frozen=True)
class ManagedReleasePublication:
    catalog_path: Path
    trusted_keyring_path: Path


class ManagedReleaseBuilder:
    """Build one signed, deterministic managed bundle behind one interface."""

    def __init__(self, signer: ManifestSigner) -> None:
        self._signer = signer

    def build(
        self,
        *,
        payload_root: str | Path,
        wheelhouse_root: str | Path,
        requirements_lock: str | Path,
        output_path: str | Path,
        app_version: str,
        entrypoint: str,
        python_requires: str,
        key_id: str,
    ) -> ManagedReleaseResult:
        payload = Path(payload_root).resolve()
        wheelhouse = Path(wheelhouse_root).resolve()
        lock = Path(requirements_lock).resolve()
        members: dict[str, bytes] = {}
        files: list[dict[str, object]] = []

        for root, prefix, role in ((payload, "payload", "payload"), (wheelhouse, "wheelhouse", "wheel")):
            for relative in regular_file_inventory(root):
                archive_path = f"{prefix}/{relative}"
                content = read_bytes(root.joinpath(*PurePosixPath(relative).parts))
                members[archive_path] = content
                files.append(_file_record(archive_path, content, role))
        lock_content = read_bytes(lock)
        members["requirements.lock"] = lock_content
        files.append(_file_record("requirements.lock", lock_content, "metadata"))
        manifest_payload = {
            "schema_version": 1,
            "app_version": app_version,
            "bundle_format": "clipai-managed-v1",
            "entrypoint": entrypoint,
            "python_requires": python_requires,
            "requirements_lock_sha256": _digest(lock_content),
            "files": sorted(files, key=lambda item: str(item["path"])),
            "signing_namespace": SIGNING_NAMESPACE,
            "key_id": key_id,
        }
        parse_install_manifest(manifest_payload)
        manifest = canonical_json_bytes(manifest_payload)
        members["install-manifest.json"] = manifest
        members["install-manifest.json.sig"] = self._signer.sign(manifest)
        output = Path(output_path).resolve()
        write_prefixed_zip(output, members)
        return ManagedReleaseResult(output, file_sha256(output), native_path(output).stat().st_size, _digest(manifest))


class OpenSshManifestSigner:
    def __init__(self, *, ssh_keygen: str | Path, private_key: str | Path, work_root: str | Path, environment: Mapping[str, str], timeout_sec: float = 12.0) -> None:
        self._ssh_keygen = Path(ssh_keygen).resolve()
        self._private_key = Path(private_key).resolve()
        self._work_root = Path(work_root).resolve()
        self._environment = dict(environment)
        self._timeout_sec = timeout_sec

    def sign(self, manifest: bytes) -> bytes:
        token = uuid.uuid4().hex[:8]
        manifest_path = self._work_root / f"manifest-{token}.json"
        signature_path = Path(f"{manifest_path}.sig")
        atomic_write_bytes(manifest_path, manifest)
        try:
            completed = subprocess.run(
                [str(self._ssh_keygen), "-q", "-Y", "sign", "-f", str(self._private_key), "-n", SIGNING_NAMESPACE, str(native_path(manifest_path))],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self._timeout_sec,
                env=self._environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                raise RuntimeError("managed release signing failed")
            return read_bytes(signature_path, maximum_size=1024 * 1024)
        finally:
            unlink_file(manifest_path)
            unlink_file(signature_path)


def write_managed_requirements_lock(
    *,
    dependency_lock: str | Path,
    clipai_wheel: str | Path,
    output_path: str | Path,
    app_version: str,
) -> Path:
    try:
        parsed_version = Version(app_version)
    except InvalidVersion as exc:
        raise ValueError("managed release version is invalid") from exc
    if str(parsed_version) != app_version:
        raise ValueError("managed release version is not normalized")
    wheel = Path(clipai_wheel).resolve()
    try:
        name, wheel_version, _build, _tags = parse_wheel_filename(wheel.name)
    except InvalidWheelFilename as exc:
        raise ValueError("ClipAI wheel filename is invalid") from exc
    if canonicalize_name(name) != "clipai" or str(wheel_version) != app_version:
        raise ValueError("ClipAI wheel does not match release version")
    dependencies = read_bytes(dependency_lock, maximum_size=4 * 1024 * 1024)
    try:
        dependency_text = dependencies.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("dependency lock is not UTF-8") from exc
    _validate_dependency_lock(dependency_text)
    header = f"clipai=={app_version} --hash=sha256:{file_sha256(wheel)}\n"
    output = Path(output_path).resolve()
    atomic_write_bytes(output, (header + dependency_text).encode("utf-8"))
    return output


def write_release_publication(
    *,
    result: ManagedReleaseResult,
    catalog_path: str | Path,
    trusted_keyring: str | Path,
    trusted_keyring_output: str | Path,
    app_version: str,
    bundle_url: str,
    key_id: str,
    minimum_launcher_version: str,
    generated_at: str,
) -> ManagedReleasePublication:
    bundle = Path(result.bundle_path).resolve()
    if (
        not native_path(bundle).is_file()
        or native_path(bundle).stat().st_size != result.bundle_size
        or file_sha256(bundle) != result.bundle_sha256
    ):
        raise ValueError("managed bundle result identity is invalid")
    keyring = load_trusted_release_keyring(trusted_keyring)
    if key_id == TEST_KEY_ID or key_id not in keyring.verification_keys():
        raise ValueError("release key must be trusted for production")
    catalog = {
        "schema_version": 1,
        "catalog_kind": CATALOG_KIND,
        "channel": "stable",
        "generated_at": generated_at,
        "releases": [{
            "version": app_version,
            "bundle_url": bundle_url,
            "bundle_sha256": result.bundle_sha256,
            "bundle_size": result.bundle_size,
            "manifest_sha256": result.manifest_sha256,
            "key_id": key_id,
            "minimum_launcher_version": minimum_launcher_version,
        }],
    }
    atomic_write_json(catalog_path, catalog)
    try:
        parse_catalog(read_bytes(catalog_path))
        published_keyring = Path(trusted_keyring_output).resolve()
        copy_file_atomically(
            trusted_keyring,
            published_keyring,
            maximum_size=1024 * 1024,
        )
        load_trusted_release_keyring(published_keyring)
    except Exception:
        unlink_file(catalog_path)
        unlink_file(trusted_keyring_output)
        raise
    return ManagedReleasePublication(Path(catalog_path).resolve(), published_keyring)


def _validate_dependency_lock(content: str) -> None:
    logical: list[str] = []
    current = ""
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current = f"{current} {stripped}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        logical.append(current)
        current = ""
    if current:
        logical.append(current)
    if not logical:
        raise ValueError("dependency lock is empty")
    for requirement in logical:
        name = requirement.split("==", 1)[0].strip()
        if canonicalize_name(name) == "clipai":
            raise ValueError("dependency lock must not contain ClipAI")
        if "==" not in requirement or "--hash=sha256:" not in requirement:
            raise ValueError("dependency lock requirements must be pinned with hashes")


def _file_record(path: str, content: bytes, role: str) -> dict[str, object]:
    return {"path": path, "size": len(content), "sha256": _digest(content), "role": role}


def _digest(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()
