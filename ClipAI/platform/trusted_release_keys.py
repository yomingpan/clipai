from __future__ import annotations

from pathlib import Path
import re

from ClipAI.core.update_signing import TEST_KEY_ID, TrustedReleaseKey, TrustedReleaseKeyring
from ClipAI.platform.managed_update_fs import read_json


KEYRING_KIND = "clipai-managed-update-trusted-keys-v1"
_ROOT_FIELDS = {"schema_version", "keyring_kind", "keys"}
_KEY_FIELDS = {"key_id", "algorithm", "public_key", "key_kind"}
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class TrustedReleaseKeyringError(ValueError):
    pass


def load_trusted_release_keyring(path: str | Path) -> TrustedReleaseKeyring:
    try:
        payload = read_json(path)
        if set(payload) != _ROOT_FIELDS:
            raise TrustedReleaseKeyringError("trusted keyring fields are invalid")
        if payload["schema_version"] != 1 or payload["keyring_kind"] != KEYRING_KIND:
            raise TrustedReleaseKeyringError("trusted keyring identity is invalid")
        raw_keys = payload["keys"]
        if not isinstance(raw_keys, list) or not raw_keys:
            raise TrustedReleaseKeyringError("trusted keyring must contain keys")
        keys = tuple(_parse_key(raw) for raw in raw_keys)
    except TrustedReleaseKeyringError:
        raise
    except Exception as exc:
        raise TrustedReleaseKeyringError("trusted keyring is invalid") from exc
    identities = [key.key_id for key in keys]
    if len(set(identities)) != len(identities):
        raise TrustedReleaseKeyringError("trusted key identities must be unique")
    return TrustedReleaseKeyring(keys)


def _parse_key(raw: object) -> TrustedReleaseKey:
    if not isinstance(raw, dict) or set(raw) != _KEY_FIELDS:
        raise TrustedReleaseKeyringError("trusted key fields are invalid")
    key_id = _text(raw["key_id"], "key_id")
    algorithm = _text(raw["algorithm"], "algorithm")
    public_key = _text(raw["public_key"], "public_key")
    key_kind = _text(raw["key_kind"], "key_kind")
    if _KEY_ID.fullmatch(key_id) is None:
        raise TrustedReleaseKeyringError("trusted key identity is invalid")
    if algorithm != "ssh-ed25519" or not public_key.startswith("ssh-ed25519 "):
        raise TrustedReleaseKeyringError("trusted key algorithm is invalid")
    try:
        public_key.encode("ascii")
    except UnicodeError as exc:
        raise TrustedReleaseKeyringError("trusted public key must be ASCII") from exc
    if key_kind not in {"production", "test_fixture"}:
        raise TrustedReleaseKeyringError("trusted key kind is invalid")
    if (key_kind == "test_fixture") != (key_id == TEST_KEY_ID):
        raise TrustedReleaseKeyringError("test key identity is misclassified")
    return TrustedReleaseKey(key_id, algorithm, public_key, key_kind)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TrustedReleaseKeyringError(f"trusted key {field} is invalid")
    return value
