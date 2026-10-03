"""Build an unsigned local acceptance Setup, not an official release asset.

Uses the shared signed bundle builder and the production installation engine.
No GitHub publication, developer credentials, or official signing keys.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from zipfile import ZipFile

from packaging.utils import parse_wheel_filename

from ClipAI.core.update_signing import TEST_KEY_ID
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner
from experiments.first_install.fetch_candidates import INPUTS, extract, require_safe_member


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(args) -> Path:
    repo = Path(__file__).resolve().parents[2]
    root = args.output_root.resolve() / f"preview-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    stage = root / "stage"
    stage.mkdir()
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    for component, archive in (("runtime", args.runtime_archive), ("verifier", args.verifier_archive)):
        identity = inputs[component]
        if archive.stat().st_size != identity["size"] or sha(archive) != identity["sha256"]:
            raise ValueError("candidate archive identity mismatch")
        extract(archive, root / component, identity["format"])
    shutil.copytree(root / "runtime/python", stage / "runtime",
                    ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc"))
    (stage / "tools").mkdir()
    tools_source = root / "verifier/OpenSSH-Win64"
    for name in ("ssh-keygen.exe", "libcrypto.dll", "LICENSE.txt", "NOTICE.txt"):
        shutil.copy2(tools_source / name, stage / "tools" / name)
    engine = stage / "setup-engine"
    shutil.copytree(repo / "ClipAI", engine / "ClipAI", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(repo / "ClipAI/ui/assets/clipai.ico", engine / "clipai.ico")
    packaging_wheels = list(args.wheelhouse.glob("packaging-*.whl"))
    if len(packaging_wheels) != 1:
        raise ValueError("one pinned packaging wheel is required")
    with ZipFile(packaging_wheels[0]) as wheel:
        for member in wheel.infolist():
            require_safe_member(member.filename)
        wheel.extractall(engine)
    (engine / "entry.py").write_text(
        "import os, sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from ClipAI.app.first_install_bootstrap import main\n"
        "raise SystemExit(main(bootstrap_root=Path(__file__).resolve().parent.parent, environment=dict(os.environ)))\n", encoding="utf-8")
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    for wheel in args.wheelhouse.glob("*.whl"):
        if parse_wheel_filename(wheel.name)[0] != "clipai":
            shutil.copy2(wheel, wheelhouse / wheel.name)
    # Rebuild the actual changed app. Build backend is caller-supplied tooling;
    # record it, and prohibit index/network dependency resolution in this step.
    build_source = root / "build-source"
    shutil.copytree(repo / "ClipAI", build_source / "ClipAI", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("main.py", "pyproject.toml", "README.md"):
        shutil.copy2(repo / name, build_source / name)
    result = subprocess.run([str(args.build_python), "-m", "pip", "wheel", "--no-index",
                             "--no-build-isolation", "--no-deps", "--wheel-dir", str(wheelhouse), str(build_source)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("offline app wheel build failed")
    app_wheels = [p for p in wheelhouse.glob("*.whl") if parse_wheel_filename(p.name)[0] == "clipai"]
    if len(app_wheels) != 1:
        raise ValueError("one ClipAI wheel is required")
    version = str(parse_wheel_filename(app_wheels[0].name)[1])
    lock = root / "requirements.lock"
    rows = []
    inventory = []
    for wheel in sorted(wheelhouse.glob("*.whl")):
        name, wheel_version, _build, _tags = parse_wheel_filename(wheel.name)
        rows.append(f"{name}=={wheel_version} --hash=sha256:{sha(wheel)}")
        inventory.append({"filename": wheel.name, "size": wheel.stat().st_size, "sha256": sha(wheel)})
    lock.write_text("\n".join(rows) + "\n", encoding="ascii")
    payload = root / "payload"
    payload.mkdir()
    shutil.copy2(repo / "main.py", payload / "main.py")
    shutil.copytree(repo / "config", payload / "config", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    key = root / "candidate-signing-key"
    tool = stage / "tools/ssh-keygen.exe"
    key_id = f"local-acceptance-{uuid.uuid4().hex}"
    assert key_id != TEST_KEY_ID
    environment = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PROGRAMDATA", "TEMP", "TMP"}}
    environment["PATH"] = ""
    try:
        generated = subprocess.run([str(tool), "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                                   env=environment, capture_output=True, check=False)
        if generated.returncode:
            raise RuntimeError("local candidate signing key generation failed")
        public = key.with_suffix(".pub").read_text(encoding="ascii").strip()
        # 'production' is the existing manifest-verification key class, not an
        # official publisher certificate. This key authorizes only this local
        # candidate, and is distinct from TEST_KEY_ID and the official keyring.
        keyring = {"schema_version": 1, "keyring_kind": "clipai-managed-update-trusted-keys-v1",
                   "keys": [{"key_id": key_id, "algorithm": "ssh-ed25519", "public_key": public, "key_kind": "production"}]}
        (engine / "managed-update-trusted-keys.json").write_text(json.dumps(keyring) + "\n", encoding="utf-8")
        release = ManagedReleaseBuilder(OpenSshManifestSigner(
            ssh_keygen=tool, private_key=key, work_root=root / "sign-work", environment=environment,
        )).build(payload_root=payload, wheelhouse_root=wheelhouse, requirements_lock=lock,
                output_path=stage / "bundle.zip", app_version=version, entrypoint="payload/main.py",
                python_requires=">=3.12,<3.13", key_id=key_id)
    finally:
        key.unlink(missing_ok=True)
        key.with_suffix(".pub").unlink(missing_ok=True)
    metadata = {"schema_version": 1, "kind": "clipai-local-acceptance-candidate",
                "product": "ClipAI Preview", "registry_name": "ClipAI.LocalAcceptance.Preview",
                "version": version, "key_id": key_id, "official_release": False,
                "authenticode": "unsigned", "inputs": inputs,
                "release": {k: v for k, v in asdict(release).items() if k != "bundle_path"}}
    (engine / "candidate.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    output = root / "output"
    compiled = subprocess.run([str(args.compiler), f"/DStageRoot={stage}", f"/DOutputRoot={output}",
                               f"/DAppVersion={version}", str(Path(__file__).with_name("preview_setup.iss"))],
                              capture_output=True, text=True, check=False)
    if compiled.returncode:
        (root / "compiler-errors.txt").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
        raise RuntimeError("Setup compilation failed; see compiler-errors.txt")
    setup = output / f"ClipAI-Preview-{version}-Setup.exe"
    report = {"kind": "local_acceptance_candidate", "created_at": datetime.now(timezone.utc).isoformat(),
              "version": version, "setup_size": setup.stat().st_size, "setup_sha256": sha(setup),
              "setup_filename": setup.name, "official_release": False, "authenticode": "unsigned",
              "clean_vm_gate": "not_covered", "publisher_signing": "not_covered",
              "local_manifest_key_only": True, "candidate_private_key_removed": not key.exists(),
              "wheelhouse": inventory, "metadata": metadata}
    (output / "build-evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"setup": str(setup), "stage": str(stage), "sha256": sha(setup)}))
    return setup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-archive", required=True, type=Path)
    parser.add_argument("--verifier-archive", required=True, type=Path)
    parser.add_argument("--wheelhouse", required=True, type=Path)
    parser.add_argument("--build-python", required=True, type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/first-install-preview"))
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
