"""Build ClipAI's one signed managed-release bundle."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil

from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-root", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--requirements-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--entrypoint", default="payload/main.py")
    parser.add_argument("--python-requires", default=">=3.12,<3.13")
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args()
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen is None:
        parser.error("Windows OpenSSH ssh-keygen is required")
    signer = OpenSshManifestSigner(ssh_keygen=ssh_keygen, private_key=args.private_key, work_root=args.work_root, environment=dict(os.environ))
    result = ManagedReleaseBuilder(signer).build(
        payload_root=args.payload_root,
        wheelhouse_root=args.wheelhouse,
        requirements_lock=args.requirements_lock,
        output_path=args.output,
        app_version=args.app_version,
        entrypoint=args.entrypoint,
        python_requires=args.python_requires,
        key_id=args.key_id,
    )
    print(f"bundle={result.bundle_path}")
    print(f"bundle_sha256={result.bundle_sha256}")
    print(f"manifest_sha256={result.manifest_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
