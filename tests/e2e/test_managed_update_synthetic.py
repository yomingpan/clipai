import json
from pathlib import Path

from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.managed_update import transaction_id
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.managed_update_fs import extract_prefixed_zip, read_json
from ClipAI.platform.update_artifacts import read_artifact, write_artifact
from ClipAI.platform.update_bundle import parse_install_manifest
from ClipAI.platform.update_catalog import parse_catalog, select_update


class _SyntheticSigner:
    def sign(self, manifest: bytes) -> bytes:
        return b"synthetic-signature:" + manifest[:16]


def test_synthetic_catalog_to_extracted_bundle_and_request(tmp_path: Path):
    payload = tmp_path / "payload-source"
    wheelhouse = tmp_path / "wheelhouse-source"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('synthetic candidate')\n", encoding="utf-8")
    (wheelhouse / "clipai.whl").write_bytes(b"synthetic-wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==3.8.0\n", encoding="utf-8")
    built = ManagedReleaseBuilder(_SyntheticSigner()).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=lock,
        output_path=tmp_path / "clipai-3.8.0.zip",
        app_version="3.8.0",
        entrypoint="payload/main.py",
        python_requires=">=3.12,<3.13",
        key_id="synthetic-key",
    )
    bundle = built.bundle_path
    catalog = parse_catalog(json.dumps({
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": [{"version": "3.8.0", "bundle_url": "https://example.invalid/clipai.zip", "bundle_sha256": built.bundle_sha256, "bundle_size": built.bundle_size, "manifest_sha256": built.manifest_sha256, "key_id": "synthetic-key", "minimum_launcher_version": "1.0"}],
    }).encode())
    release = select_update(catalog, installed_version="3.7.3", launcher_version="1.0")
    assert release is not None
    extracted_root = tmp_path / "candidate"
    extract_prefixed_zip(bundle, extracted_root)
    parsed_manifest = parse_install_manifest(read_json(extracted_root / "install-manifest.json"))
    request = UpdateRequestArtifact(transaction_id("synthetic-transaction"), "2026-09-13T00:00:00+00:00", "3.7.3", parsed_manifest.app_version, bundle.resolve(), (tmp_path / "install").resolve(), (tmp_path / "shared").resolve(), "synthetic-install")
    request_path = tmp_path / "request.json"
    write_artifact(request_path, request)
    assert read_artifact(request_path, expected_kind="request", expected_transaction_id="synthetic-transaction") == request
