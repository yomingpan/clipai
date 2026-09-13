from pathlib import Path

import pytest

from ClipAI.platform.managed_update_fs import atomic_write_json
from ClipAI.platform.trusted_release_keys import (
    TrustedReleaseKeyringError,
    load_trusted_release_keyring,
)


TEST_KEY_ID = "clipai-managed-update-test-v1"


def _write(path: Path, keys: list[dict[str, str]]) -> None:
    atomic_write_json(path, {
        "schema_version": 1,
        "keyring_kind": "clipai-managed-update-trusted-keys-v1",
        "keys": keys,
    })


def test_keyring_exposes_production_keys_and_requires_explicit_test_policy(tmp_path: Path):
    path = tmp_path / "managed-update-trusted-keys.json"
    _write(path, [
        {
            "key_id": "release-2026",
            "algorithm": "ssh-ed25519",
            "public_key": "ssh-ed25519 AAAAproduction release-2026",
            "key_kind": "production",
        },
        {
            "key_id": TEST_KEY_ID,
            "algorithm": "ssh-ed25519",
            "public_key": "ssh-ed25519 AAAAtest fixture",
            "key_kind": "test_fixture",
        },
    ])

    keyring = load_trusted_release_keyring(path)

    assert keyring.verification_keys() == {
        "release-2026": "ssh-ed25519 AAAAproduction release-2026",
    }
    assert keyring.verification_keys(allow_test_keys=True)[TEST_KEY_ID] == (
        "ssh-ed25519 AAAAtest fixture"
    )


@pytest.mark.parametrize(
    "keys",
    [
        [],
        [
            {"key_id": "duplicate", "algorithm": "ssh-ed25519", "public_key": "ssh-ed25519 AAAAone", "key_kind": "production"},
            {"key_id": "duplicate", "algorithm": "ssh-ed25519", "public_key": "ssh-ed25519 AAAAtwo", "key_kind": "production"},
        ],
        [
            {"key_id": "release-test", "algorithm": "ssh-ed25519", "public_key": "ssh-ed25519 AAAAtest", "key_kind": "test_fixture"},
        ],
        [
            {"key_id": TEST_KEY_ID, "algorithm": "ssh-ed25519", "public_key": "ssh-ed25519 AAAAtest", "key_kind": "production"},
        ],
    ],
)
def test_keyring_rejects_empty_duplicate_or_misclassified_key_identity(tmp_path: Path, keys):
    path = tmp_path / "managed-update-trusted-keys.json"
    _write(path, keys)

    with pytest.raises(TrustedReleaseKeyringError):
        load_trusted_release_keyring(path)
