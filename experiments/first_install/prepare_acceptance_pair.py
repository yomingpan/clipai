"""Prepare source-bound A/B technical candidates with one disposable authority.

Reuses the existing builders and admission boundary. Never installs an app,
publishes assets, changes OS trust, or reads an official signing secret.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import uuid

from packaging.utils import parse_wheel_filename
from packaging.version import Version

from ClipAI.core.update_bundle import BundleAdmissionRequest
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner, write_release_publication
from ClipAI.platform.managed_update_fs import atomic_write_json, file_sha256
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_catalog import parse_catalog
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager
from scripts.build_setup_release import verify_source_commit
from scripts.verify_release_assets import verify


def require_newer_version(a: str, b: str) -> None:
    if str(Version(a)) != a or str(Version(b)) != b or Version(b) <= Version(a):
        raise ValueError("B must have a normalized, genuinely newer app version")


def export_source(commit: str, target: Path) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("a full Git source commit is required")
    completed = subprocess.run(["git", "archive", commit], capture_output=True, check=True, timeout=30)
    target.mkdir(exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout)) as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name or not (member.isdir() or member.isfile()):
                raise ValueError("unsupported source archive member")
            destination = target.joinpath(*path.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
    # Parse only the project's literal static version, not build-tool settings.
    match = re.search(r'(?ms)^\[project\]\s*.*?^version = "([^"]+)"$', (target / "pyproject.toml").read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("source has no static project version")
    return match.group(1)


def run(*arguments: str | Path, timeout: int = 600) -> None:
    subprocess.run([str(argument) for argument in arguments], check=True, timeout=timeout)


def prepare(args) -> Path:
    original = verify(args.a_assets)
    a_proof = json.loads((args.a_assets / "provenance.json").read_text(encoding="utf-8"))
    a_release, = parse_catalog((args.a_assets / "catalog.json").read_bytes()).releases
    a_bundle = args.a_assets / f"clipai-managed-{a_release.version}.zip"
    verify_source_commit(a_bundle, a_proof["source_commit"])
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    b_version = export_source(args.b_source_commit, root / "b-source")
    require_newer_version(a_release.version, b_version)
    environment = {**os.environ}
    admission = root / "original-admission"
    admission.mkdir()
    admitted_bundle = admission / "bundle.zip"
    shutil.copyfile(a_bundle, admitted_bundle)
    original_keys = load_trusted_release_keyring(args.a_assets / "managed-update-trusted-keys.json")
    verified = VerifiedManagedBundleStager(manifest_verifier=Ed25519ManifestVerifier(
        ssh_keygen=args.ssh_keygen, trusted_keys=original_keys.verification_keys(),
        work_root=root / "original-verification", environment=environment,
    )).stage(BundleAdmissionRequest(admission, admitted_bundle, a_release.bundle_size,
                                    a_release.bundle_sha256, a_release.manifest_sha256,
                                    a_release.version, a_release.key_id))
    a_wheels = verified.staging_root / "wheelhouse"
    b_wheels = root / "b-wheelhouse"
    b_wheels.mkdir()
    for wheel in a_wheels.glob("*.whl"):
        if parse_wheel_filename(wheel.name)[0] != "clipai":
            shutil.copyfile(wheel, b_wheels / wheel.name)
    run(args.build_python, "-m", "pip", "wheel", "--no-index", "--no-build-isolation", "--no-deps",
        "--wheel-dir", b_wheels, root / "b-source")
    b_apps = [wheel for wheel in b_wheels.glob("*.whl") if parse_wheel_filename(wheel.name)[0] == "clipai"]
    if len(b_apps) != 1 or str(parse_wheel_filename(b_apps[0].name)[1]) != b_version:
        raise ValueError("B wheel metadata does not match source version")
    b_lock = root / "b-requirements.lock"
    b_lock.write_text("\n".join(f"{name}=={version} --hash=sha256:{file_sha256(wheel)}"
        for wheel in sorted(b_wheels.glob("*.whl"))
        for name, version, _, _ in [parse_wheel_filename(wheel.name)]) + "\n", encoding="ascii")
    key = root / "pair-private-key"
    keyring = root / "pair-public-keyring.json"
    key_id = "local-acceptance-pair-" + uuid.uuid4().hex
    reports = {}
    try:
        run(args.ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", key, timeout=30)
        public = key.with_suffix(".pub").read_text(encoding="ascii").strip()
        atomic_write_json(keyring, {"schema_version": 1, "keyring_kind": "clipai-managed-update-trusted-keys-v1",
            "keys": [{"key_id": key_id, "algorithm": "ssh-ed25519", "public_key": public, "key_kind": "production"}]})
        for label, version, commit, payload, wheels, lock in (
            ("A", a_release.version, a_proof["source_commit"], verified.staging_root / "payload", a_wheels, verified.staging_root / "requirements.lock"),
            ("B", b_version, args.b_source_commit, root / "b-payload", b_wheels, b_lock),
        ):
            if label == "B":
                payload.mkdir()
                shutil.copyfile(root / "b-source/main.py", payload / "main.py")
                shutil.copytree(root / "b-source/config", payload / "config")
            assets = root / (label + "-publication")
            assets.mkdir()
            result = ManagedReleaseBuilder(OpenSshManifestSigner(
                ssh_keygen=args.ssh_keygen, private_key=key, work_root=root / (label + "-sign-work"), environment=environment,
            )).build(payload_root=payload, wheelhouse_root=wheels, requirements_lock=lock,
                     output_path=assets / f"clipai-managed-{version}.zip", app_version=version,
                     entrypoint="payload/main.py", python_requires=verified.manifest.python_requires, key_id=key_id)
            write_release_publication(result=result, catalog_path=assets / "catalog.json", trusted_keyring=keyring,
                trusted_keyring_output=assets / "managed-update-trusted-keys.json", app_version=version,
                bundle_url=f"https://github.com/yomingpan/clipai/releases/download/v{version}/clipai-managed-{version}.zip",
                key_id=key_id, minimum_launcher_version=a_release.minimum_launcher_version,
                generated_at=datetime.now(timezone.utc).isoformat())
            delivery = root / label
            run(sys.executable, "-m", "scripts.build_setup_release", "--bundle", result.bundle_path,
                "--catalog", assets / "catalog.json", "--keyring", keyring, "--inputs", args.inputs,
                "--runtime-archive", args.runtime_archive, "--verifier-archive", args.verifier_archive,
                "--compiler", args.compiler, "--output-root", delivery,
                "--tag", "v" + version, "--source-commit", commit, "--technical-candidate")
            run(sys.executable, "-m", "scripts.verify_packaged_app", "--stage", delivery / "stage",
                "--output", delivery / "output/packaged-smoke.json")
            run(sys.executable, "-m", "scripts.verify_setup_extraction", "--assets", delivery / "output")
            reports[label] = {**verify(delivery / "output"), "version": version, "source_commit": commit}
    finally:
        key.unlink(missing_ok=True)
        key.with_suffix(".pub").unlink(missing_ok=True)
    report = {"kind": "clipai-local-acceptance-pair", "original_a": original, "candidates": reports,
        "key_id": key_id, "keyring_sha256": file_sha256(keyring), "private_key_removed": not key.exists(),
        "about_update": "pending", "clean_vm": "deferred_by_user", "publisher_signing": "pending", "public_release": False}
    atomic_write_json(root / "pair.json", report)
    print(json.dumps(report))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("a-assets", "build-python", "ssh-keygen", "runtime-archive", "verifier-archive", "compiler", "inputs", "output-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--b-source-commit", required=True)
    prepare(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
