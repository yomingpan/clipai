from pathlib import Path

from ClipAI.core.update_bundle import BundleAdmissionRequest
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager


class _Signer:
    def sign(self, manifest: bytes) -> bytes:
        return b"synthetic:" + manifest[:16]


class _Verifier:
    def __init__(self) -> None:
        self.key_ids: list[str] = []

    def verify(self, manifest_path, signature_path, *, key_id):
        self.key_ids.append(key_id)


def test_stager_admits_catalog_bound_bundle_once_and_returns_immutable_source(tmp_path: Path):
    transaction_root = (tmp_path / "shared" / "managed-update" / "transactions" / "tx-1").resolve()
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('managed')\n", encoding="utf-8")
    (wheelhouse / "clipai.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==2.0\n", encoding="utf-8")
    built = ManagedReleaseBuilder(_Signer()).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=lock,
        output_path=transaction_root / "release.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.11",
        key_id="release-key",
    )
    verifier = _Verifier()
    stager = VerifiedManagedBundleStager(manifest_verifier=verifier)

    verified = stager.stage(BundleAdmissionRequest(
        transaction_root=transaction_root,
        bundle_path=built.bundle_path,
        bundle_size=built.bundle_size,
        bundle_sha256=built.bundle_sha256,
        manifest_sha256=built.manifest_sha256,
        expected_version="2.0",
        key_id="release-key",
    ))
    built.bundle_path.write_bytes(b"replaced after admission")

    assert verified.staging_root == transaction_root / "verified-bundle"
    assert verified.manifest.app_version == "2.0"
    assert verified.manifest.entrypoint == "payload/main.py"
    assert (verified.staging_root / "payload" / "main.py").read_text(encoding="utf-8") == "print('managed')\n"
    assert verifier.key_ids == ["release-key"]
