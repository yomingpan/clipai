from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import subprocess
import uuid
from typing import Protocol

from ClipAI.platform.managed_update_fs import (
    atomic_write_bytes,
    file_sha256,
    native_path,
    read_bytes,
    regular_file_inventory,
    unlink_file,
    write_prefixed_zip,
)
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


def _file_record(path: str, content: bytes, role: str) -> dict[str, object]:
    return {"path": path, "size": len(content), "sha256": _digest(content), "role": role}


def _digest(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()
