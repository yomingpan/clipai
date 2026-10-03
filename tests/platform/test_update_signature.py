import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from ClipAI.platform.managed_update_fs import atomic_write_bytes
from ClipAI.platform.managed_release_builder import OpenSshManifestSigner
from ClipAI.platform.update_signature import (
    Ed25519ManifestVerifier,
    SIGNING_NAMESPACE,
    TEST_KEY_ID,
    SignatureVerificationError,
    canonical_json_bytes,
)


def _signed_manifest(tmp_path: Path, *, namespace: str = SIGNING_NAMESPACE) -> tuple[Path, Path, str, Path]:
    ssh_keygen = shutil.which("ssh-keygen")
    assert ssh_keygen is not None, "Windows OpenSSH ssh-keygen is required"
    private_key = tmp_path / "fixture-key"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
        capture_output=True,
    )
    manifest = tmp_path / "install-manifest.json"
    atomic_write_bytes(
        manifest,
        canonical_json_bytes({"key_id": TEST_KEY_ID, "schema_version": 1}),
    )
    subprocess.run(
        [ssh_keygen, "-q", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(manifest)],
        check=True,
        capture_output=True,
    )
    public_key = private_key.with_suffix(".pub").read_text(encoding="ascii")
    return manifest, Path(f"{manifest}.sig"), public_key, Path(ssh_keygen)


def _verifier(tmp_path: Path, public_key: str, executable: Path, *, allow_test_keys: bool, namespace: str = SIGNING_NAMESPACE):
    return Ed25519ManifestVerifier(
        ssh_keygen=executable,
        trusted_keys={TEST_KEY_ID: public_key},
        work_root=tmp_path / "verify",
        environment=dict(os.environ),
        allow_test_keys=allow_test_keys,
        namespace=namespace,
    )


def test_real_ed25519_fixture_signature_round_trips(tmp_path: Path):
    manifest, signature, public_key, executable = _signed_manifest(tmp_path)
    _verifier(tmp_path, public_key, executable, allow_test_keys=True).verify(
        manifest,
        signature,
        key_id=TEST_KEY_ID,
    )


def test_modified_manifest_is_rejected(tmp_path: Path):
    manifest, signature, public_key, executable = _signed_manifest(tmp_path)
    atomic_write_bytes(manifest, canonical_json_bytes({"schema_version": 2}))
    with pytest.raises(SignatureVerificationError, match="invalid"):
        _verifier(tmp_path, public_key, executable, allow_test_keys=True).verify(
            manifest,
            signature,
            key_id=TEST_KEY_ID,
        )


def test_noncanonical_manifest_is_rejected_before_ssh(tmp_path: Path):
    manifest, signature, public_key, executable = _signed_manifest(tmp_path)
    manifest.write_text(json.dumps({"schema_version": 1}, indent=2), encoding="utf-8")
    with pytest.raises(SignatureVerificationError, match="canonical"):
        _verifier(tmp_path, public_key, executable, allow_test_keys=True).verify(
            manifest,
            signature,
            key_id=TEST_KEY_ID,
        )


def test_production_policy_rejects_test_fixture_identity(tmp_path: Path):
    manifest, signature, public_key, executable = _signed_manifest(tmp_path)
    with pytest.raises(SignatureVerificationError, match="forbidden"):
        _verifier(tmp_path, public_key, executable, allow_test_keys=False).verify(
            manifest,
            signature,
            key_id=TEST_KEY_ID,
        )


def test_openssh_signer_adapter_interoperates_with_verifier(tmp_path: Path):
    manifest, _old_signature, public_key, executable = _signed_manifest(tmp_path)
    signer = OpenSshManifestSigner(
        ssh_keygen=executable,
        private_key=tmp_path / "fixture-key",
        work_root=tmp_path / "signer-work",
        environment=dict(os.environ),
    )
    signature = tmp_path / "adapter.sig"
    atomic_write_bytes(signature, signer.sign(manifest.read_bytes()))
    _verifier(tmp_path, public_key, executable, allow_test_keys=True).verify(
        manifest,
        signature,
        key_id=TEST_KEY_ID,
    )
