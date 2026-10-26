import json
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import pytest

from ClipAI.core.managed_update import ManagedUpdateFailure
from ClipAI.platform.managed_release_builder import (
    ManagedReleaseBuilder, OpenSshManifestSigner, write_release_publication,
)
from ClipAI.platform.managed_update_fs import file_sha256
from scripts.verify_release_assets import verify


def identity(path):
    return {"size": path.stat().st_size, "sha256": file_sha256(path)}


@pytest.fixture
def signed_assets(tmp_path):
    executable = shutil.which("ssh-keygen")
    assert executable
    key = tmp_path / "key"
    subprocess.run([executable, "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                   check=True, capture_output=True)
    payload, wheels = tmp_path / "payload", tmp_path / "wheels"
    payload.mkdir()
    wheels.mkdir()
    (payload / "main.py").write_bytes(b"payload")
    (wheels / "clipai.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"lock")
    keys = tmp_path / "managed-update-trusted-keys.json"
    keys.write_text(json.dumps({"schema_version": 1,
        "keyring_kind": "clipai-managed-update-trusted-keys-v1",
        "keys": [{"key_id": "release-2026", "algorithm": "ssh-ed25519",
                  "public_key": key.with_suffix(".pub").read_text(encoding="ascii").strip(),
                  "key_kind": "production"}]}), encoding="utf-8")
    result = ManagedReleaseBuilder(OpenSshManifestSigner(
        ssh_keygen=executable, private_key=key, work_root=tmp_path / "signing",
        environment=dict(os.environ),
    )).build(payload_root=payload, wheelhouse_root=wheels, requirements_lock=lock,
             output_path=tmp_path / "clipai-managed-2.0.zip", app_version="2.0",
             entrypoint="payload/main.py", python_requires=">=3.10", key_id="release-2026")
    catalog = tmp_path / "catalog.json"
    write_release_publication(result=result, catalog_path=catalog, trusted_keyring=keys,
        trusted_keyring_output=tmp_path / "published-keys.json", app_version="2.0",
        bundle_url="https://github.com/yomingpan/clipai/releases/download/v2.0/clipai-managed-2.0.zip",
        key_id="release-2026", minimum_launcher_version="1.0", generated_at="2026-10-07T00:00:00+00:00")
    setup = tmp_path / "Setup.exe"
    setup.write_bytes(b"setup")
    (tmp_path / "notices").mkdir()
    (tmp_path / "notices/LICENSE").write_bytes(b"notice")
    proof = {"tag": "v2.0", "app_version": "2.0", "setup": {"filename": setup.name, **identity(setup)},
             "bundle": identity(result.bundle_path), "catalog": identity(catalog), "keyring": identity(keys),
             "manifest_sha256": result.manifest_sha256, "requirements_lock": identity(lock),
             "wheels": {"clipai.whl": identity(wheels / "clipai.whl")}, "inputs": {}}
    (tmp_path / "provenance.json").write_text(json.dumps(proof), encoding="utf-8")
    for name in ("packaged-smoke.json", "setup-extraction.json"):
        (tmp_path / name).write_text(json.dumps({"status": "passed",
            "setup_sha256": file_sha256(setup), "bundle_sha256": result.bundle_sha256}), encoding="utf-8")
    return tmp_path


def test_release_gate_admits_authentic_bundle(signed_assets, monkeypatch):
    from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager
    sentinel = signed_assets / "verified-bundle" / "user-file"
    sentinel.parent.mkdir()
    sentinel.write_bytes(b"preserve")
    roots = []
    original = VerifiedManagedBundleStager.stage
    def stage(self, request):
        roots.append(request.transaction_root)
        return original(self, request)
    monkeypatch.setattr(VerifiedManagedBundleStager, "stage", stage)
    assert verify(signed_assets)["status"] == "passed"
    assert len(roots) == 1 and not roots[0].exists()
    assert sentinel.read_bytes() == b"preserve"


@pytest.mark.parametrize("damage", ["signature", "payload", "missing", "extra"])
def test_release_gate_rejects_inner_damage_with_rebound_outer_hashes(signed_assets, damage, monkeypatch):
    from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager
    roots = []
    original = VerifiedManagedBundleStager.stage
    def stage(self, request):
        roots.append(request.transaction_root)
        return original(self, request)
    monkeypatch.setattr(VerifiedManagedBundleStager, "stage", stage)
    bundle = signed_assets / "clipai-managed-2.0.zip"
    with ZipFile(bundle) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    prefix = "clipai-managed-v1/"
    if damage == "signature":
        files[prefix + "install-manifest.json.sig"] = b"invalid signature"
    elif damage == "payload":
        files[prefix + "payload/main.py"] = b"changed"
    elif damage == "missing":
        del files[prefix + "payload/main.py"]
    else:
        files[prefix + "payload/extra.py"] = b"undeclared"
    with ZipFile(bundle, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    catalog_path = signed_assets / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["releases"][0].update(bundle_sha256=file_sha256(bundle), bundle_size=bundle.stat().st_size)
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    proof_path = signed_assets / "provenance.json"
    proof = json.loads(proof_path.read_text())
    proof.update(bundle=identity(bundle), catalog=identity(catalog_path))
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(ManagedUpdateFailure):
        verify(signed_assets)
    assert len(roots) == 1 and not roots[0].exists()
    assert bundle.is_file()


def test_release_gate_requires_complete_wheel_provenance(signed_assets):
    path = signed_assets / "provenance.json"
    proof = json.loads(path.read_text())
    proof["wheels"] = {}
    path.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete provenance"):
        verify(signed_assets)
