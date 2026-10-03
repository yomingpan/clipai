"""A2 compatibility spike for explicitly supplied OpenSSH tools, never release admission."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from ClipAI.core.update_signing import SIGNING_NAMESPACE, TEST_KEY_ID
from ClipAI.platform.managed_release_builder import OpenSshManifestSigner
from ClipAI.platform.managed_update_fs import atomic_write_json
from ClipAI.platform.update_signature import (
    Ed25519ManifestVerifier, SignatureVerificationError, canonical_json_bytes,
)
from experiments.first_install.probe_runtime import isolated_environment


def probe(tools_root: Path, output_root: Path) -> tuple[Path, dict]:
    tool = tools_root.resolve() / "ssh-keygen.exe"
    if not tool.is_file():
        raise ValueError("supply a trusted unpacked OpenSSH tools directory")
    root = output_root.resolve() / f"verifier-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    private_key = root / "test-fixture-key"
    report = {
        "schema_version": 1, "probe_kind": "first-install-local-verifier",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed", "namespace": SIGNING_NAMESPACE,
        "tool_sha256": hashlib.sha256(tool.read_bytes()).hexdigest(),
        "test_key_only": True, "content_recorded": False,
        "empty_child_path": True, "clean_vm_gate": "not_covered",
        "distribution_admission": "not_covered",
    }
    try:
        environment = isolated_environment(root)
        report["phase"] = "generate_test_key"
        completed = subprocess.run(
            [str(tool), "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
            env=environment, cwd=root, capture_output=True, timeout=20, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        report["key_generation_exit_code"] = completed.returncode
        if completed.returncode:
            raise RuntimeError("fixture key generation failed")
        public_key = private_key.with_suffix(".pub").read_text(encoding="ascii")
        report["phase"] = "existing_signer_and_verifier"
        signer = OpenSshManifestSigner(
            ssh_keygen=tool, private_key=private_key,
            work_root=root / "sign-work", environment=environment,
        )
        verifier = Ed25519ManifestVerifier(
            ssh_keygen=tool, trusted_keys={TEST_KEY_ID: public_key},
            work_root=root / "verify-work", environment=environment, allow_test_keys=True,
        )
        manifest = root / "synthetic-manifest.json"
        signature = root / "synthetic-manifest.json.sig"
        original = canonical_json_bytes({"probe": "synthetic-verifier-only"})
        manifest.write_bytes(original)
        signature.write_bytes(signer.sign(original))
        verifier.verify(manifest, signature, key_id=TEST_KEY_ID)
        report["valid_signature"] = "passed"
        manifest.write_bytes(canonical_json_bytes({"probe": "tampered"}))
        try:
            verifier.verify(manifest, signature, key_id=TEST_KEY_ID)
        except SignatureVerificationError:
            report["tamper_rejected"] = "passed"
        else:
            raise RuntimeError("tampered fixture was accepted")
        manifest.write_bytes(original)
        production_verifier = Ed25519ManifestVerifier(
            ssh_keygen=tool, trusted_keys={TEST_KEY_ID: public_key},
            work_root=root / "production-policy", environment=environment,
        )
        try:
            production_verifier.verify(manifest, signature, key_id=TEST_KEY_ID)
        except SignatureVerificationError:
            report["test_key_rejected_by_production"] = "passed"
        else:
            raise RuntimeError("production policy accepted the test key")
        report.update(status="passed", phase="complete")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report["error_type"] = type(exc).__name__
    finally:
        # These exact files are created only by this operation. Never retain keys
        # in the saved report or in the candidate download/archive inventory.
        private_key.unlink(missing_ok=True)
        private_key.with_suffix(".pub").unlink(missing_ok=True)
        report["fixture_private_key_removed"] = not private_key.exists()
        atomic_write_json(root / "report.json", report)
    return root / "report.json", report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-root", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/first-install-verifier"))
    args = parser.parse_args()
    report_path, report = probe(args.tools_root, args.output_root)
    print(json.dumps({"status": report["status"], "report": str(report_path), "distribution_admission": "not_covered"}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
