from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
import subprocess
import uuid

from ClipAI.core.update_signing import SIGNING_NAMESPACE, TEST_KEY_ID
from ClipAI.platform.managed_update_fs import (
    atomic_write_bytes,
    native_path,
    read_bytes,
    unlink_file,
)


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SignatureVerificationError(ValueError):
    pass


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


class Ed25519ManifestVerifier:
    """Verify canonical manifests through an injected OpenSSH executable."""

    def __init__(
        self,
        *,
        ssh_keygen: str | Path,
        trusted_keys: Mapping[str, str],
        work_root: str | Path,
        environment: Mapping[str, str],
        allow_test_keys: bool = False,
        timeout_sec: float = 12.0,
        namespace: str = SIGNING_NAMESPACE,
    ) -> None:
        self._ssh_keygen = Path(ssh_keygen).resolve()
        self._trusted_keys = dict(trusted_keys)
        self._work_root = Path(work_root).resolve()
        self._environment = dict(environment)
        self._allow_test_keys = allow_test_keys
        self._timeout_sec = timeout_sec
        self._namespace = namespace

    def verify(
        self,
        manifest_path: str | Path,
        signature_path: str | Path,
        *,
        key_id: str,
    ) -> None:
        public_key = self._trusted_keys.get(key_id)
        if _KEY_ID.fullmatch(key_id) is None or public_key is None:
            raise SignatureVerificationError("manifest key is not trusted")
        if key_id == TEST_KEY_ID and not self._allow_test_keys:
            raise SignatureVerificationError("test signing key is forbidden")
        normalized_key = _normalize_public_key(public_key)
        manifest = read_bytes(manifest_path, maximum_size=4 * 1024 * 1024)
        try:
            payload = json.loads(manifest.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SignatureVerificationError("manifest is not valid UTF-8 JSON") from exc
        if canonical_json_bytes(payload) != manifest:
            raise SignatureVerificationError("manifest JSON is not canonical")

        principal = f"clipai-managed-update:{key_id}"
        allowed_signers = self._work_root / f"allowed-signers-{uuid.uuid4().hex[:8]}"
        atomic_write_bytes(
            allowed_signers,
            f"{principal} {normalized_key}\n".encode("ascii"),
        )
        try:
            try:
                completed = subprocess.run(
                    [
                        str(self._ssh_keygen),
                        "-Y",
                        "verify",
                        "-f",
                        str(native_path(allowed_signers)),
                        "-I",
                        principal,
                        "-n",
                        self._namespace,
                        "-s",
                        str(native_path(signature_path)),
                    ],
                    input=manifest,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=self._timeout_sec,
                    env=self._environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SignatureVerificationError("signature verifier unavailable") from exc
            if completed.returncode != 0:
                raise SignatureVerificationError("manifest signature is invalid")
        finally:
            unlink_file(allowed_signers)


def _normalize_public_key(value: str) -> str:
    fields = value.strip().split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise SignatureVerificationError("trusted key is not Ed25519")
    try:
        normalized = f"{fields[0]} {fields[1]}".encode("ascii").decode("ascii")
    except UnicodeError as exc:
        raise SignatureVerificationError("trusted key is not ASCII") from exc
    return normalized
