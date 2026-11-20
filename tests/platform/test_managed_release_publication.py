from pathlib import Path

import pytest

from ClipAI.core.update_signing import TEST_KEY_ID
from ClipAI.platform.managed_release_builder import (
    ManagedReleaseResult,
    write_managed_requirements_lock,
    write_release_publication,
)
from ClipAI.platform.managed_update_fs import file_sha256, read_bytes, read_json
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_catalog import parse_catalog


def test_release_lock_binds_exact_clipai_wheel_to_hashed_dependency_lock(tmp_path: Path) -> None:
    dependency_lock = tmp_path / "dependencies.lock"
    dependency_lock.write_text(
        "certifi==2026.1.1 \\\n+    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    wheel = tmp_path / "clipai-3.8.0-py3-none-any.whl"
    wheel.write_bytes(b"signed release wheel")

    output = write_managed_requirements_lock(
        dependency_lock=dependency_lock,
        clipai_wheel=wheel,
        output_path=tmp_path / "requirements.lock",
        app_version="3.8.0",
    )

    content = read_bytes(output).decode("utf-8")
    assert content.startswith(
        f"clipai==3.8.0 --hash=sha256:{file_sha256(wheel)}\n"
    )
    assert "certifi==2026.1.1" in content


def test_release_lock_rejects_unhashed_or_duplicate_clipai_input(tmp_path: Path) -> None:
    wheel = tmp_path / "clipai-3.8.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    dependency_lock = tmp_path / "dependencies.lock"
    dependency_lock.write_text("certifi==2026.1.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        write_managed_requirements_lock(
            dependency_lock=dependency_lock,
            clipai_wheel=wheel,
            output_path=tmp_path / "requirements.lock",
            app_version="3.8.0",
        )
    dependency_lock.write_text(
        "clipai==3.8.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ClipAI"):
        write_managed_requirements_lock(
            dependency_lock=dependency_lock,
            clipai_wheel=wheel,
            output_path=tmp_path / "requirements.lock",
            app_version="3.8.0",
        )


def test_publication_writes_catalog_bound_to_bundle_and_production_keyring(tmp_path: Path) -> None:
    bundle = tmp_path / "clipai-managed-3.8.0.zip"
    bundle.write_bytes(b"bundle")
    result = ManagedReleaseResult(bundle, file_sha256(bundle), 6, "b" * 64)
    source_keyring = tmp_path / "trusted.json"
    source_keyring.write_text(
        '{"schema_version":1,"keyring_kind":"clipai-managed-update-trusted-keys-v1",'
        '"keys":[{"key_id":"release-2026","algorithm":"ssh-ed25519",'
        '"public_key":"ssh-ed25519 AAAAproduction release-2026","key_kind":"production"}]}\n',
        encoding="utf-8",
    )

    publication = write_release_publication(
        result=result,
        catalog_path=tmp_path / "catalog.json",
        trusted_keyring=source_keyring,
        trusted_keyring_output=tmp_path / "managed-update-trusted-keys.json",
        app_version="3.8.0",
        bundle_url="https://github.com/yomingpan/clipai/releases/download/v3.8.0/clipai-managed-3.8.0.zip",
        key_id="release-2026",
        minimum_launcher_version="3.7.3",
        generated_at="2026-09-14T00:00:00+00:00",
    )

    catalog = parse_catalog(read_bytes(publication.catalog_path))
    assert catalog.releases[0].bundle_sha256 == result.bundle_sha256
    assert catalog.releases[0].bundle_size == 6
    assert catalog.releases[0].manifest_sha256 == "b" * 64
    assert load_trusted_release_keyring(publication.trusted_keyring_path).verification_keys() == {
        "release-2026": "ssh-ed25519 AAAAproduction release-2026"
    }


def test_publication_rejects_test_or_untrusted_signing_identity(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"bundle")
    result = ManagedReleaseResult(bundle, file_sha256(bundle), 6, "b" * 64)
    keyring = tmp_path / "trusted.json"
    keyring.write_text(
        '{"schema_version":1,"keyring_kind":"clipai-managed-update-trusted-keys-v1",'
        f'"keys":[{{"key_id":"{TEST_KEY_ID}","algorithm":"ssh-ed25519",'
        f'"public_key":"ssh-ed25519 AAAAtest fixture","key_kind":"test_fixture"}}]}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="production"):
        write_release_publication(
            result=result,
            catalog_path=tmp_path / "catalog.json",
            trusted_keyring=keyring,
            trusted_keyring_output=tmp_path / "published-keyring.json",
            app_version="3.8.0",
            bundle_url="https://example.com/bundle.zip",
            key_id=TEST_KEY_ID,
            minimum_launcher_version="3.7.3",
            generated_at="2026-09-14T00:00:00+00:00",
        )
    assert not (tmp_path / "catalog.json").exists()
