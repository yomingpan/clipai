from pathlib import Path
import json
import shutil
import subprocess
import sys

import pytest

from ClipAI.platform.managed_update_fs import file_sha256, read_bytes
from ClipAI.platform.update_catalog import parse_catalog


ROOT = Path(__file__).resolve().parents[2]


def test_release_cli_prepares_lock_for_exact_built_wheel(tmp_path: Path) -> None:
    dependency_lock = tmp_path / "dependencies.lock"
    dependency_lock.write_text(
        "certifi==2026.1.1 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    wheel = tmp_path / "clipai-3.8.0-py3-none-any.whl"
    wheel.write_bytes(b"release wheel")
    output = tmp_path / "requirements.lock"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_managed_release.py"),
            "--prepare-lock",
            "--dependency-lock", str(dependency_lock),
            "--clipai-wheel", str(wheel),
            "--requirements-lock", str(output),
            "--app-version", "3.8.0",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8").startswith(
        f"clipai==3.8.0 --hash=sha256:{file_sha256(wheel)}\n"
    )


def test_release_cli_self_verifies_signature_and_catalog_before_publication(tmp_path: Path) -> None:
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen is None:
        pytest.skip("Windows OpenSSH is unavailable")
    private_key = tmp_path / "release-key"
    generated = subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    public_key = private_key.with_suffix(".pub").read_text(encoding="ascii").strip()
    keyring = tmp_path / "trusted.json"
    keyring.write_text(json.dumps({
        "schema_version": 1,
        "keyring_kind": "clipai-managed-update-trusted-keys-v1",
        "keys": [{
            "key_id": "release-2026",
            "algorithm": "ssh-ed25519",
            "public_key": public_key,
            "key_kind": "production",
        }],
    }), encoding="utf-8")
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('ClipAI')\n", encoding="utf-8")
    (wheelhouse / "clipai-3.8.0-py3-none-any.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==3.8.0 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    bundle = tmp_path / "clipai-managed-3.8.0.zip"
    catalog = tmp_path / "catalog.json"
    published_keyring = tmp_path / "managed-update-trusted-keys.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_managed_release.py"),
            "--payload-root", str(payload),
            "--wheelhouse", str(wheelhouse),
            "--requirements-lock", str(lock),
            "--output", str(bundle),
            "--app-version", "3.8.0",
            "--key-id", "release-2026",
            "--private-key", str(private_key),
            "--work-root", str(tmp_path / "work"),
            "--catalog-output", str(catalog),
            "--bundle-url", "https://github.com/yomingpan/clipai/releases/download/v3.8.0/clipai-managed-3.8.0.zip",
            "--trusted-keyring", str(keyring),
            "--trusted-keyring-output", str(published_keyring),
            "--generated-at", "2026-09-14T00:00:00+00:00",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    release = parse_catalog(read_bytes(catalog)).releases[0]
    assert release.bundle_sha256 == file_sha256(bundle)
    assert release.bundle_size == bundle.stat().st_size
    assert published_keyring.read_bytes() == keyring.read_bytes()
