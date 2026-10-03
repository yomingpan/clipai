"""Build ClipAI's one signed managed-release bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import uuid

from ClipAI.platform.managed_release_builder import (
    ManagedReleaseBuilder,
    OpenSshManifestSigner,
    write_managed_requirements_lock,
    write_release_publication,
)
from ClipAI.platform.managed_update_fs import extract_prefixed_zip, file_sha256, remove_tree
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-lock", action="store_true")
    parser.add_argument("--dependency-lock", type=Path)
    parser.add_argument("--clipai-wheel", type=Path)
    parser.add_argument("--payload-root", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--requirements-lock", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--app-version")
    parser.add_argument("--entrypoint", default="payload/main.py")
    parser.add_argument("--python-requires", default=">=3.12,<3.13")
    parser.add_argument("--key-id")
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--catalog-output", type=Path)
    parser.add_argument("--bundle-url")
    parser.add_argument("--minimum-launcher-version", default="3.7.3")
    parser.add_argument("--trusted-keyring", type=Path)
    parser.add_argument("--trusted-keyring-output", type=Path)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    if args.prepare_lock:
        dependency_lock = _required(parser, args.dependency_lock, "--dependency-lock")
        clipai_wheel = _required(parser, args.clipai_wheel, "--clipai-wheel")
        requirements_lock = _required(parser, args.requirements_lock, "--requirements-lock")
        app_version = _required(parser, args.app_version, "--app-version")
        output = write_managed_requirements_lock(
            dependency_lock=dependency_lock,
            clipai_wheel=clipai_wheel,
            output_path=requirements_lock,
            app_version=app_version,
        )
        print(f"requirements_lock={output}")
        return 0

    payload_root = _required(parser, args.payload_root, "--payload-root")
    wheelhouse = _required(parser, args.wheelhouse, "--wheelhouse")
    requirements_lock = _required(parser, args.requirements_lock, "--requirements-lock")
    output = _required(parser, args.output, "--output")
    app_version = _required(parser, args.app_version, "--app-version")
    key_id = _required(parser, args.key_id, "--key-id")
    private_key = _required(parser, args.private_key, "--private-key")
    work_root = _required(parser, args.work_root, "--work-root")
    catalog_output = _required(parser, args.catalog_output, "--catalog-output")
    bundle_url = _required(parser, args.bundle_url, "--bundle-url")
    trusted_keyring = _required(parser, args.trusted_keyring, "--trusted-keyring")
    trusted_keyring_output = _required(
        parser, args.trusted_keyring_output, "--trusted-keyring-output"
    )
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen is None:
        parser.error("Windows OpenSSH ssh-keygen is required")
    signer = OpenSshManifestSigner(ssh_keygen=ssh_keygen, private_key=private_key, work_root=work_root, environment=dict(os.environ))
    result = ManagedReleaseBuilder(signer).build(
        payload_root=payload_root,
        wheelhouse_root=wheelhouse,
        requirements_lock=requirements_lock,
        output_path=output,
        app_version=app_version,
        entrypoint=args.entrypoint,
        python_requires=args.python_requires,
        key_id=key_id,
    )
    verification_root = Path(work_root).resolve() / f"verify-{uuid.uuid4().hex[:8]}"
    try:
        extract_prefixed_zip(result.bundle_path, verification_root)
        manifest_path = verification_root / "install-manifest.json"
        if file_sha256(manifest_path) != result.manifest_sha256:
            raise RuntimeError("built manifest digest does not match release result")
        keyring = load_trusted_release_keyring(trusted_keyring)
        Ed25519ManifestVerifier(
            ssh_keygen=ssh_keygen,
            trusted_keys=keyring.verification_keys(),
            work_root=Path(work_root).resolve() / "signature-verification",
            environment=dict(os.environ),
        ).verify(
            manifest_path,
            verification_root / "install-manifest.json.sig",
            key_id=key_id,
        )
    finally:
        remove_tree(verification_root)
    publication = write_release_publication(
        result=result,
        catalog_path=catalog_output,
        trusted_keyring=trusted_keyring,
        trusted_keyring_output=trusted_keyring_output,
        app_version=app_version,
        bundle_url=bundle_url,
        key_id=key_id,
        minimum_launcher_version=args.minimum_launcher_version,
        generated_at=args.generated_at or datetime.now(timezone.utc).isoformat(),
    )
    print(f"bundle={result.bundle_path}")
    print(f"bundle_sha256={result.bundle_sha256}")
    print(f"bundle_size={result.bundle_size}")
    print(f"manifest_sha256={result.manifest_sha256}")
    print(f"catalog={publication.catalog_path}")
    print(f"trusted_keyring={publication.trusted_keyring_path}")
    return 0


def _required(parser: argparse.ArgumentParser, value, option: str):
    if value is None or value == "":
        parser.error(f"{option} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
