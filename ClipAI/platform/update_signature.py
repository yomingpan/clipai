from __future__ import annotations

from collections.abc import Mapping
import base64
import binascii
import hashlib
import hmac
import json
from pathlib import Path
import re

from ClipAI.core.update_signing import SIGNING_NAMESPACE, TEST_KEY_ID
from ClipAI.platform.managed_update_fs import (
    read_bytes,
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
    """Verify canonical manifests and OpenSSH SSHSIG v1 with Ed25519."""

    def __init__(
        self,
        *,
        trusted_keys: Mapping[str, str],
        allow_test_keys: bool = False,
        namespace: str = SIGNING_NAMESPACE,
    ) -> None:
        self._trusted_keys = dict(trusted_keys)
        self._allow_test_keys = allow_test_keys
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

        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        try:
            trusted_blob = base64.b64decode(normalized_key.split()[1], validate=True)
            trusted = _Strings(trusted_blob)
            if trusted.string() != b"ssh-ed25519":
                raise ValueError("key algorithm")
            key = trusted.string()
            trusted.finish()
            if len(key) != 32:
                raise ValueError("key length")
            lines = read_bytes(signature_path, maximum_size=16 * 1024).splitlines()
            if len(lines) < 3 or lines[0] != b"-----BEGIN SSH SIGNATURE-----" or lines[-1] != b"-----END SSH SIGNATURE-----":
                raise ValueError("signature armor")
            blob = base64.b64decode(b"".join(lines[1:-1]), validate=True)
            if blob[:6] != b"SSHSIG" or blob[6:10] != b"\0\0\0\1":
                raise ValueError("signature version")
            fields = _Strings(blob[10:])
            if not hmac.compare_digest(fields.string(), trusted_blob):
                raise ValueError("signature key")
            namespace, reserved, algorithm = fields.string(), fields.string(), fields.string()
            if not namespace or namespace != self._namespace.encode("utf-8"):
                raise ValueError("signature namespace")
            if algorithm not in (b"sha256", b"sha512"):
                raise ValueError("signature hash")
            signature = _Strings(fields.string())
            fields.finish()
            if signature.string() != b"ssh-ed25519":
                raise ValueError("signature algorithm")
            signed_bytes = signature.string()
            signature.finish()
            if len(signed_bytes) != 64:
                raise ValueError("signature length")
            digest = hashlib.new(algorithm.decode("ascii"), manifest).digest()
            message = b"SSHSIG" + b"".join(_string(value) for value in (namespace, reserved, algorithm, digest))
            Ed25519PublicKey.from_public_bytes(key).verify(signed_bytes, message)
        except (ValueError, binascii.Error, UnicodeError, InvalidSignature) as exc:
            raise SignatureVerificationError("manifest signature is invalid") from exc


def _string(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


class _Strings:
    """Bounded RFC4253 string reader; no allocation follows untrusted lengths."""

    def __init__(self, content: bytes) -> None:
        self._content = content
        self._offset = 0

    def string(self) -> bytes:
        if self._offset + 4 > len(self._content):
            raise ValueError("truncated SSH string")
        size = int.from_bytes(self._content[self._offset:self._offset + 4], "big")
        start = self._offset + 4
        end = start + size
        if end > len(self._content):
            raise ValueError("truncated SSH string")
        self._offset = end
        return self._content[start:end]

    def finish(self) -> None:
        if self._offset != len(self._content):
            raise ValueError("trailing SSH data")


def _normalize_public_key(value: str) -> str:
    fields = value.strip().split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise SignatureVerificationError("trusted key is not Ed25519")
    try:
        normalized = f"{fields[0]} {fields[1]}".encode("ascii").decode("ascii")
    except UnicodeError as exc:
        raise SignatureVerificationError("trusted key is not ASCII") from exc
    return normalized
