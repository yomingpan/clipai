"""Fail closed on an incomplete candidate or an unaccepted public release."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile

from ClipAI.platform.managed_update_fs import file_sha256
from ClipAI.platform.update_catalog import parse_catalog
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring


REQUIRED_GATES = ("clean_vm_cycle", "failure_recovery", "reboot", "cross_logon_gate",
                  "native_admission", "browser_windows_trust", "first_user_result")


def _matches(path: Path, identity: dict) -> None:
    if path.stat().st_size != identity["size"] or file_sha256(path) != identity["sha256"]:
        raise ValueError(f"asset identity mismatch: {path.name}")


def verify(assets: Path, *, require_release_ready: bool = False,
           acceptance: Path | None = None, publisher: str | None = None) -> dict:
    proof = json.loads((assets / "provenance.json").read_text(encoding="utf-8"))
    release, = parse_catalog((assets / "catalog.json").read_bytes()).releases
    if proof["tag"] != "v" + release.version or proof["app_version"] != release.version:
        raise ValueError("release version mismatch")
    expected_url = f"https://github.com/yomingpan/clipai/releases/download/{proof['tag']}/clipai-managed-{release.version}.zip"
    if release.bundle_url != expected_url:
        raise ValueError("release URL mismatch")
    setup_name = proof["setup"]["filename"]
    if Path(setup_name).name != setup_name:
        raise ValueError("unsafe Setup filename")
    setup = assets / setup_name
    bundle = assets / f"clipai-managed-{release.version}.zip"
    _matches(setup, proof["setup"])
    _matches(bundle, proof["bundle"])
    _matches(assets / "catalog.json", proof["catalog"])
    _matches(assets / "managed-update-trusted-keys.json", proof["keyring"])
    keys = load_trusted_release_keyring(assets / "managed-update-trusted-keys.json").verification_keys()
    if release.key_id not in keys or release.bundle_sha256 != file_sha256(bundle) or release.bundle_size != bundle.stat().st_size:
        raise ValueError("catalog bundle/keyring mismatch")
    if release.manifest_sha256 != proof["manifest_sha256"]:
        raise ValueError("catalog manifest mismatch")
    import hashlib
    with ZipFile(bundle) as archive:
        if hashlib.sha256(archive.read("clipai-managed-v1/install-manifest.json")).hexdigest() != release.manifest_sha256:
            raise ValueError("manifest substitution")
        lock = archive.read("clipai-managed-v1/requirements.lock")
        if {"size": len(lock), "sha256": hashlib.sha256(lock).hexdigest()} != proof["requirements_lock"]:
            raise ValueError("lock substitution")
        for name, expected in proof["wheels"].items():
            content = archive.read("clipai-managed-v1/wheelhouse/" + name)
            if {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()} != expected:
                raise ValueError("wheel substitution")
    if not (assets / "notices").is_dir() or not any((assets / "notices").rglob("*")):
        raise ValueError("component notices are missing")
    smoke = json.loads((assets / "packaged-smoke.json").read_text())
    extraction = json.loads((assets / "setup-extraction.json").read_text())
    for evidence in (smoke, extraction):
        if evidence["status"] != "passed" or evidence["bundle_sha256"] != release.bundle_sha256 or evidence["setup_sha256"] != proof["setup"]["sha256"]:
            raise ValueError("candidate evidence mismatch")
    if require_release_ready:
        if proof["technical_candidate"] or proof["distribution_admission"] != "approved":
            raise ValueError("technical/unadmitted candidate cannot be published")
        if acceptance is None or not publisher:
            raise ValueError("exact candidate acceptance and publisher identity are required")
        accepted = json.loads(acceptance.read_text(encoding="utf-8"))
        if accepted["setup_sha256"] != proof["setup"]["sha256"] or accepted["bundle_sha256"] != release.bundle_sha256:
            raise ValueError("acceptance belongs to another candidate")
        if any(accepted["gates"].get(gate) != "passed" for gate in REQUIRED_GATES):
            raise ValueError("required release gates have not passed")
        # Verify the final file itself; an evidence label is not a signature.
        with tempfile.TemporaryDirectory(prefix="clipai-signature-") as temporary:
            report = Path(temporary) / "signature.json"
            script = "$s=Get-AuthenticodeSignature -LiteralPath $args[0]; @{status=$s.Status.ToString(); publisher=$s.SignerCertificate.Subject; timestamp=$s.TimeStamperCertificate.Subject} | ConvertTo-Json -Compress | Set-Content -LiteralPath $args[1] -Encoding UTF8"
            script_path = Path(temporary) / "verify.ps1"
            script_path.write_text(script, encoding="utf-8")
            subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script_path), str(setup), str(report)], check=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            signature = json.loads(report.read_text(encoding="utf-8-sig"))
        if signature["status"] != "Valid" or signature["publisher"] != publisher or not signature["timestamp"]:
            raise ValueError("final Setup publisher/timestamp verification failed")
    return {"status": "passed", "release_ready": require_release_ready, "setup_sha256": proof["setup"]["sha256"], "bundle_sha256": release.bundle_sha256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--require-release-ready", action="store_true")
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--publisher")
    args = parser.parse_args()
    print(json.dumps(verify(args.assets.resolve(), require_release_ready=args.require_release_ready,
                            acceptance=args.acceptance, publisher=args.publisher)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
