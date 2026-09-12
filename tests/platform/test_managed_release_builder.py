from pathlib import Path

import pytest

from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.managed_update_fs import extract_prefixed_zip, read_json
from ClipAI.platform.update_bundle import BundleValidationError, parse_install_manifest, verify_bundle_inventory


class Signer:
    def __init__(self) -> None:
        self.manifests: list[bytes] = []

    def sign(self, manifest: bytes) -> bytes:
        self.manifests.append(manifest)
        return b"synthetic-signature"


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (wheelhouse / "clipai-3.8.0.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==3.8.0\n", encoding="utf-8")
    return payload, wheelhouse, lock


def test_single_builder_creates_deterministic_signed_bundle(tmp_path: Path):
    payload, wheelhouse, lock = _inputs(tmp_path)
    signer = Signer()
    builder = ManagedReleaseBuilder(signer)
    first = builder.build(payload_root=payload, wheelhouse_root=wheelhouse, requirements_lock=lock, output_path=tmp_path / "first.zip", app_version="3.8.0", entrypoint="payload/main.py", python_requires=">=3.12,<3.13", key_id="release-2026")
    second = builder.build(payload_root=payload, wheelhouse_root=wheelhouse, requirements_lock=lock, output_path=tmp_path / "second.zip", app_version="3.8.0", entrypoint="payload/main.py", python_requires=">=3.12,<3.13", key_id="release-2026")
    assert first.bundle_sha256 == second.bundle_sha256
    assert signer.manifests[0] == signer.manifests[1]
    extracted = tmp_path / "extracted"
    extract_prefixed_zip(first.bundle_path, extracted)
    manifest = parse_install_manifest(read_json(extracted / "install-manifest.json"))
    verify_bundle_inventory(extracted, manifest)


def test_builder_rejects_user_owned_payload_before_writing_bundle(tmp_path: Path):
    payload, wheelhouse, lock = _inputs(tmp_path)
    (payload / ".env").write_text("SECRET=nope", encoding="utf-8")
    with pytest.raises(BundleValidationError, match="user-owned"):
        ManagedReleaseBuilder(Signer()).build(payload_root=payload, wheelhouse_root=wheelhouse, requirements_lock=lock, output_path=tmp_path / "bad.zip", app_version="3.8.0", entrypoint="payload/main.py", python_requires=">=3.12,<3.13", key_id="release-2026")
    assert not (tmp_path / "bad.zip").exists()


def test_inventory_detects_post_extraction_tampering(tmp_path: Path):
    payload, wheelhouse, lock = _inputs(tmp_path)
    result = ManagedReleaseBuilder(Signer()).build(payload_root=payload, wheelhouse_root=wheelhouse, requirements_lock=lock, output_path=tmp_path / "bundle.zip", app_version="3.8.0", entrypoint="payload/main.py", python_requires=">=3.12,<3.13", key_id="release-2026")
    extracted = tmp_path / "candidate"
    extract_prefixed_zip(result.bundle_path, extracted)
    manifest = parse_install_manifest(read_json(extracted / "install-manifest.json"))
    (extracted / "payload" / "main.py").write_text("tampered", encoding="utf-8")
    with pytest.raises(BundleValidationError, match="identity"):
        verify_bundle_inventory(extracted, manifest)
