from __future__ import annotations

from dataclasses import dataclass


SIGNING_NAMESPACE = "clipai.managed-update.manifest.v1"
TEST_KEY_ID = "clipai-managed-update-test-v1"


@dataclass(frozen=True)
class TrustedReleaseKey:
    key_id: str
    algorithm: str
    public_key: str
    key_kind: str


@dataclass(frozen=True)
class TrustedReleaseKeyring:
    keys: tuple[TrustedReleaseKey, ...]

    def verification_keys(self, *, allow_test_keys: bool = False) -> dict[str, str]:
        return {
            key.key_id: key.public_key
            for key in self.keys
            if key.key_kind == "production" or allow_test_keys
        }
