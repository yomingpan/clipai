import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.managed_update import transaction_id
from ClipAI.platform.managed_update_fs import extract_prefixed_zip, read_json
from ClipAI.platform.update_artifacts import read_artifact, write_artifact
from ClipAI.platform.update_bundle import parse_install_manifest
from ClipAI.platform.update_catalog import parse_catalog, select_update
from ClipAI.platform.update_signature import SIGNING_NAMESPACE, canonical_json_bytes


def test_synthetic_catalog_to_extracted_bundle_and_request(tmp_path: Path):
    payload = b"print('synthetic candidate')\n"
    lock = b"clipai==3.8.0\n"
    wheel = b"synthetic-wheel"
    digest = lambda value: hashlib.sha256(value).hexdigest()
    manifest_payload = {
        "schema_version": 1,
        "app_version": "3.8.0",
        "bundle_format": "clipai-managed-v1",
        "entrypoint": "payload/main.py",
        "python_requires": ">=3.12,<3.13",
        "requirements_lock_sha256": digest(lock),
        "files": [
            {"path": "payload/main.py", "size": len(payload), "sha256": digest(payload), "role": "payload"},
            {"path": "requirements.lock", "size": len(lock), "sha256": digest(lock), "role": "metadata"},
            {"path": "wheelhouse/clipai.whl", "size": len(wheel), "sha256": digest(wheel), "role": "wheel"},
        ],
        "signing_namespace": SIGNING_NAMESPACE,
        "key_id": "synthetic-key",
    }
    manifest = canonical_json_bytes(manifest_payload)
    bundle = tmp_path / "clipai-3.8.0.zip"
    with ZipFile(bundle, "w") as archive:
        archive.writestr("clipai-managed-v1/payload/main.py", payload)
        archive.writestr("clipai-managed-v1/requirements.lock", lock)
        archive.writestr("clipai-managed-v1/wheelhouse/clipai.whl", wheel)
        archive.writestr("clipai-managed-v1/install-manifest.json", manifest)
    bundle_hash = digest(bundle.read_bytes())
    catalog = parse_catalog(json.dumps({
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": [{"version": "3.8.0", "bundle_url": "https://example.invalid/clipai.zip", "bundle_sha256": bundle_hash, "bundle_size": bundle.stat().st_size, "manifest_sha256": digest(manifest), "key_id": "synthetic-key", "minimum_launcher_version": "1.0"}],
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
