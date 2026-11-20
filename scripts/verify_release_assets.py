"""Fail closed on an incomplete candidate or an unaccepted public release."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from ClipAI.platform.managed_update_fs import file_sha256
from ClipAI.platform.update_catalog import parse_catalog
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager


REQUIRED_GATES = ("clean_vm_cycle", "failure_recovery", "reboot", "cross_logon_gate",
                  "native_admission", "browser_windows_trust", "first_user_result")


def _matches(path: Path, identity: dict) -> None:
    if path.stat().st_size != identity["size"] or file_sha256(path) != identity["sha256"]:
        raise ValueError(f"asset identity mismatch: {path.name}")


def _inspect_signature(setup: Path) -> dict:
    """Inspect the final bytes rather than trusting a provenance label."""
    with tempfile.TemporaryDirectory(prefix="clipai-signature-") as temporary:
        report = Path(temporary) / "signature.json"
        script = "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $args[0]; @{status=$s.Status.ToString(); publisher=$s.SignerCertificate.Subject; timestamp=$s.TimeStamperCertificate.Subject} | ConvertTo-Json -Compress | Set-Content -LiteralPath $args[1] -Encoding UTF8"
        script_path = Path(temporary) / "verify.ps1"
        script_path.write_text(script, encoding="utf-8")
        # PowerShell 7 may export its module path to a Windows PowerShell 5.1
        # child; use that child's own built-in modules for native inspection.
        powershell_root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0"
        environment = dict(os.environ, PSModulePath=str(powershell_root / "Modules"))
        subprocess.run([str(powershell_root / "powershell.exe"), "-NoProfile", "-File", str(script_path), str(setup.resolve()), str(report)], check=True, timeout=30, env=environment,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(report.read_text(encoding="utf-8-sig"))


def verify(assets: Path, *, require_release_ready: bool = False,
           acceptance: Path | None = None, publisher: str | None = None,
           publisher_policy: str = "signed") -> dict:
    if publisher_policy not in ("signed", "unsigned"):
        raise ValueError("unknown publisher policy")
    signature = None
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
    _matches(assets / "catalog.json", proof["catalog"])
    _matches(assets / "managed-update-trusted-keys.json", proof["keyring"])
    keys = load_trusted_release_keyring(assets / "managed-update-trusted-keys.json").verification_keys()
    # Admission hashes the copied bytes once; provenance must name that same
    # catalog identity instead of independently re-reading the archive here.
    if release.key_id not in keys or proof["bundle"] != {"size": release.bundle_size, "sha256": release.bundle_sha256}:
        raise ValueError("catalog bundle/keyring mismatch")
    if release.manifest_sha256 != proof["manifest_sha256"]:
        raise ValueError("catalog manifest mismatch")
    manifest = VerifiedManagedBundleStager(
        manifest_verifier=Ed25519ManifestVerifier(trusted_keys=keys),
    ).verify_external(
        bundle_path=bundle, bundle_size=release.bundle_size,
        bundle_sha256=release.bundle_sha256, manifest_sha256=release.manifest_sha256,
        expected_version=release.version, key_id=release.key_id,
    )
    lock, = (file for file in manifest.files if file.path == "requirements.lock")
    if {"size": lock.size, "sha256": lock.sha256} != proof["requirements_lock"]:
        raise ValueError("lock substitution")
    wheels = {file.path.removeprefix("wheelhouse/"): {"size": file.size, "sha256": file.sha256}
              for file in manifest.files if file.role == "wheel"}
    if wheels != proof["wheels"]:
        raise ValueError("wheel substitution or incomplete provenance")
    if not (assets / "notices").is_dir() or not any((assets / "notices").rglob("*")):
        raise ValueError("component notices are missing")
    for source in proof["inputs"].get("corresponding_sources", {}).values():
        filename = source["filename"]
        if (not filename or Path(filename).name != filename
                or filename in (".", "..") or "\\" in filename or ":" in filename):
            raise ValueError("unsafe corresponding source filename")
        _matches(assets / "sources" / filename, source)
    smoke = json.loads((assets / "packaged-smoke.json").read_text())
    extraction = json.loads((assets / "setup-extraction.json").read_text())
    for evidence in (smoke, extraction):
        if evidence["status"] != "passed" or evidence["bundle_sha256"] != release.bundle_sha256 or evidence["setup_sha256"] != proof["setup"]["sha256"]:
            raise ValueError("candidate evidence mismatch")
    if require_release_ready:
        if proof["technical_candidate"] or proof["distribution_admission"] != "approved":
            raise ValueError("technical/unadmitted candidate cannot be published")
        if acceptance is None or (publisher_policy == "signed" and not publisher):
            raise ValueError("exact candidate acceptance and publisher identity are required")
        accepted = json.loads(acceptance.read_text(encoding="utf-8"))
        if accepted.get("publisher_policy", "signed") != publisher_policy:
            raise ValueError("acceptance publisher policy mismatch")
        if accepted["setup_sha256"] != proof["setup"]["sha256"] or accepted["bundle_sha256"] != release.bundle_sha256:
            raise ValueError("acceptance belongs to another candidate")
        if any(accepted["gates"].get(gate) != "passed" for gate in REQUIRED_GATES):
            raise ValueError("required release gates have not passed")
        signature = _inspect_signature(setup)
        if publisher_policy == "unsigned" and signature["status"] != "NotSigned":
            raise ValueError("final Setup does not match explicit unsigned publisher policy")
        if publisher_policy == "signed" and (signature["status"] != "Valid" or signature["publisher"] != publisher or not signature["timestamp"]):
            raise ValueError("final Setup publisher/timestamp verification failed")
    return {"status": "passed", "release_ready": require_release_ready,
            "publisher_policy": publisher_policy, "authenticode": signature["status"] if signature else "unchecked",
            "setup_sha256": proof["setup"]["sha256"], "bundle_sha256": release.bundle_sha256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--require-release-ready", action="store_true")
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--publisher")
    parser.add_argument("--publisher-policy", choices=("signed", "unsigned"), default="signed")
    args = parser.parse_args()
    print(json.dumps(verify(args.assets.resolve(), require_release_ready=args.require_release_ready,
                            acceptance=args.acceptance, publisher=args.publisher, publisher_policy=args.publisher_policy)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
