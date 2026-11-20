"""Offline installed-wheel import proof, separate from clean-machine acceptance."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

from ClipAI.core.managed_update import transaction_id
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.managed_update_fs import atomic_write_json, file_sha256


PROBE = """
import importlib.metadata, json, pathlib, sys
import ClipAI, ClipAI.app.first_install_bootstrap, main
import cryptography, cffi, pycparser, _cffi_backend
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
assert cryptography.__version__ == '50.0.2'
dist = importlib.metadata.distribution('clipai')
assert dist.version == sys.argv[1]
prefix = pathlib.Path(sys.prefix).resolve()
paths = [pathlib.Path(m.__file__).resolve() for m in (ClipAI, main, cryptography, cffi, pycparser, _cffi_backend)]
assert all(p.is_relative_to(prefix) for p in paths), 'import escaped installed wheel'
direct = dist.read_text('direct_url.json')
assert not direct or not json.loads(direct).get('dir_info', {}).get('editable'), 'editable install'
print(json.dumps({'version': dist.version, 'executable': sys.executable, 'import_paths': [str(p) for p in paths], 'editable': False}))
"""

BOOTSTRAP_PROBE = """
import pathlib, sys
sys.path.insert(0, sys.argv[1])
import cryptography, cffi, pycparser, _cffi_backend
assert cryptography.__version__ == '50.0.2'
root = pathlib.Path(sys.argv[1]).resolve()
assert all(pathlib.Path(module.__file__).resolve().is_relative_to(root) for module in (cryptography, cffi, pycparser, _cffi_backend))
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
keys = load_trusted_release_keyring(root / 'managed-update-trusted-keys.json')
manifest = pathlib.Path(sys.argv[2])
Ed25519ManifestVerifier(trusted_keys=keys.verification_keys()).verify(manifest / 'install-manifest.json', manifest / 'install-manifest.json.sig', key_id=sys.argv[3])
"""


def verify(stage: Path, output: Path) -> Path:
    root = stage.parent
    metadata = json.loads((stage / "setup-engine/candidate.json").read_text(encoding="utf-8"))
    admitted = root / "admission/verified-bundle"
    # Use precisely the tree admitted by SetupReleaseBuilder, copied by the
    # same materializer used for install/update; no dependency resolution.
    from ClipAI.platform.prepared_managed_payload import PreparedManagedPayloadMaterializer
    from ClipAI.platform.update_bundle import parse_install_manifest
    from ClipAI.core.update_bundle import VerifiedManagedBundle
    manifest = parse_install_manifest(json.loads((admitted / "install-manifest.json").read_text(encoding="utf-8")))
    smoke = root / "packaged-smoke"
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA"}}
    env.update(PATH="", PYTHONPATH=str(Path.cwd()), PYTHONHOME="poisoned", PIP_NO_INDEX="1")
    clean_env = {k: v for k, v in env.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    subprocess.run([str(stage / "runtime/python.exe"), "-I", "-c", BOOTSTRAP_PROBE,
                    str(stage / "setup-engine"), str(admitted), metadata["key_id"]],
                   cwd=root, env=clean_env, check=True, capture_output=True, text=True, timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    candidate = PreparedManagedPayloadMaterializer(candidate_builder=OfflineCandidateEnvironmentBuilder(
        environment=env, timeout_sec=240)).prepare(
            VerifiedManagedBundle(admitted, manifest), target_root=smoke,
            transaction_id=transaction_id("packaged-smoke"), base_python=(stage / "runtime/python.exe").resolve())
    completed = subprocess.run([str(candidate.python), "-I", "-c", PROBE, metadata["version"]],
                               cwd=root, env={k: v for k, v in env.items() if k not in {"PYTHONPATH", "PYTHONHOME"}},
                               capture_output=True, text=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        raise RuntimeError("installed-wheel import proof failed")
    report = {"status": "passed", "evidence_level": "local-packaged-app", "clean_vm": False,
              "network_isolation": False, "offline_pip": True, "path_empty": True,
              "bundle_sha256": file_sha256(stage / "bundle.zip"), "identity": json.loads(completed.stdout),
              "setup_sha256": json.loads((root / "output/provenance.json").read_text())["setup"]["sha256"]}
    atomic_write_json(output, report)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(verify(args.stage.resolve(), args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
