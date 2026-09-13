from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.core.update_signing import TEST_KEY_ID
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.managed_install import ManagedInstallLayout
from ClipAI.platform.managed_installer import FilesystemManagedInstaller
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner
from ClipAI.platform.managed_update_fs import (
    atomic_write_bytes,
    atomic_write_json,
    file_sha256,
    native_path,
    regular_file_inventory,
)
from ClipAI.platform.managed_update_lifecycle import SubprocessManagedApplicationLifecycle
from ClipAI.platform.update_signature import Ed25519ManifestVerifier


class _Lease:
    def close(self) -> None:
        return


class _Gate:
    def acquire(self) -> _Lease:
        return _Lease()


def _clean_environment() -> dict[str, str]:
    blocked = {
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PIP_CONFIG_FILE",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() not in blocked}
    environment.update({
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_NO_INDEX": "1",
        "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONNOUSERSITE": "1",
    })
    return environment


def _build_fixture_wheel(tmp_path: Path, base_python: Path) -> tuple[Path, str]:
    source = tmp_path / "wheel-source"
    package = source / "src" / "clipai_smoke"
    package.mkdir(parents=True)
    atomic_write_bytes(package / "__init__.py", b"SMOKE = True\n")
    atomic_write_bytes(source / "pyproject.toml", textwrap.dedent("""
        [build-system]
        requires = ["setuptools>=68", "wheel"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "clipai"
        version = "2.0"
        requires-python = ">=3.12,<3.13"

        [tool.setuptools.packages.find]
        where = ["src"]
        """).lstrip().encode("utf-8"))
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    completed = subprocess.run(
        [
            str(base_python),
            "-I",
            "-m",
            "pip",
            "wheel",
            "--isolated",
            "--no-index",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(native_path(wheelhouse)),
            str(native_path(source)),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_clean_environment(),
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert completed.returncode == 0, completed.stderr
    wheels = regular_file_inventory(wheelhouse)
    assert len(wheels) == 1 and wheels[0].endswith(".whl")
    wheel = wheelhouse / wheels[0]
    return wheelhouse, file_sha256(wheel)


def _health_entrypoint() -> bytes:
    return textwrap.dedent("""
        from __future__ import annotations

        import argparse
        from datetime import datetime, timezone
        import importlib.metadata
        import importlib.util
        import json
        import os
        from pathlib import Path
        import sys
        import uuid

        parser = argparse.ArgumentParser()
        parser.add_argument("command")
        parser.add_argument("--shared-root", required=True)
        parser.add_argument("--transaction-id", required=True)
        parser.add_argument("--install-root", required=True)
        parser.add_argument("--launch-attempt-id", required=True)
        parser.add_argument("--expected-version", required=True)
        args = parser.parse_args()

        actual_version = importlib.metadata.version("clipai")
        polluted = any(name in os.environ for name in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"))
        machine_truststore = any(
            importlib.util.find_spec(name) is not None
            for name in ("pip_system_certs", "truststore")
        )
        healthy = (
            args.command == "launch"
            and actual_version == args.expected_version
            and not polluted
            and not machine_truststore
            and os.environ.get("CLIPAI_INSTANCE_NAME") == "managed-bundle-smoke"
        )
        payload = {
            "schema_version": 1,
            "artifact_kind": "startup_health",
            "transaction_id": args.transaction_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "launch_attempt_id": args.launch_attempt_id,
            "expected_version": args.expected_version,
            "actual_version": actual_version,
            "executable_path": str(Path(sys.executable).resolve()),
            "healthy": healthy,
        }
        root = Path(args.shared_root) / "managed-update" / "transactions" / args.transaction_id
        root.mkdir(parents=True, exist_ok=True)
        destination = root / "startup-health.json"
        temporary = root / f".startup-health.{uuid.uuid4().hex}.tmp"
        with temporary.open("x", encoding="utf-8", newline="\\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        raise SystemExit(0 if healthy else 1)
        """).lstrip().encode("utf-8")


def _signed_bundle(tmp_path: Path, base_python: Path):
    ssh_keygen = shutil.which("ssh-keygen")
    assert ssh_keygen is not None, "Windows OpenSSH ssh-keygen is required"
    private_key = tmp_path / "fixture-key"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
        capture_output=True,
    )
    wheelhouse, wheel_hash = _build_fixture_wheel(tmp_path, base_python)
    payload = tmp_path / "payload"
    payload.mkdir()
    atomic_write_bytes(payload / "main.py", _health_entrypoint())
    requirements_lock = tmp_path / "requirements.lock"
    atomic_write_bytes(
        requirements_lock,
        f"clipai==2.0 --hash=sha256:{wheel_hash}\n".encode("ascii"),
    )
    signer = OpenSshManifestSigner(
        ssh_keygen=ssh_keygen,
        private_key=private_key,
        work_root=tmp_path / "sign-work",
        environment=_clean_environment(),
    )
    built = ManagedReleaseBuilder(signer).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=requirements_lock,
        output_path=tmp_path / "clipai-2.0.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.12,<3.13",
        key_id=TEST_KEY_ID,
    )
    public_key = private_key.with_suffix(".pub").read_text(encoding="ascii")
    verifier = Ed25519ManifestVerifier(
        ssh_keygen=ssh_keygen,
        trusted_keys={TEST_KEY_ID: public_key},
        work_root=tmp_path / "verify-work",
        environment=_clean_environment(),
        allow_test_keys=True,
    )
    keyring = tmp_path / "trusted-keys.json"
    atomic_write_json(keyring, {
        "schema_version": 1,
        "keyring_kind": "clipai-managed-update-trusted-keys-v1",
        "keys": [{
            "key_id": TEST_KEY_ID,
            "algorithm": "ssh-ed25519",
            "public_key": public_key.strip(),
            "key_kind": "test_fixture",
        }],
    })
    return built, verifier, keyring


@pytest.mark.integration
def test_real_managed_bundle_builds_offline_and_launches_identity_bound_health(tmp_path: Path) -> None:
    base_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    built, verifier, keyring = _signed_bundle(tmp_path, base_python)
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    poisoned_environment = {
        **os.environ,
        "VIRTUAL_ENV": "parent-venv",
        "PYTHONPATH": "parent-imports",
        "PYTHONHOME": "parent-home",
        "PIP_CONFIG_FILE": str(tmp_path / "machine-pip.ini"),
        "PIP_INDEX_URL": "https://network.invalid/simple",
        "PIP_EXTRA_INDEX_URL": "https://network.invalid/extra",
        "CLIPAI_INSTANCE_NAME": "managed-bundle-smoke",
    }
    installer = FilesystemManagedInstaller(
        manifest_verifier=verifier,
        candidate_builder=OfflineCandidateEnvironmentBuilder(
            environment=poisoned_environment,
            timeout_sec=120,
        ),
        trusted_keyring_path=keyring,
        update_gate_factory=lambda _root: _Gate(),
    )
    command = InstallManagedCommand(
        shared_root=shared_root,
        install_root=install_root,
        transaction_id=transaction_id("bundle-install"),
        expected_version="2.0",
        bundle_path=built.bundle_path,
        bundle_size=built.bundle_size,
        bundle_sha256=built.bundle_sha256,
        manifest_sha256=built.manifest_sha256,
        key_id=TEST_KEY_ID,
        managed_install_id="managed-bundle-smoke",
        launcher_version="1.0",
        base_python=base_python,
    )

    installed = installer.install(command)
    layout = ManagedInstallLayout(
        install_root=install_root,
        shared_root=shared_root,
        manifest_verifier=verifier,
    )
    assert layout.prove_current_install() == installed
    processes: list[subprocess.Popen[str]] = []

    def start_process(arguments, environment, cwd):
        process = subprocess.Popen(
            list(arguments),
            cwd=native_path(cwd),
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        processes.append(process)
        return process

    lifecycle = SubprocessManagedApplicationLifecycle(
        layout=layout,
        environment=poisoned_environment,
        shutdown=lambda _transaction_id: None,
        now=lambda: "2026-09-13T00:00:00+00:00",
        start_process=start_process,
    )
    launch = lifecycle.launch(
        version_root=installed.root,
        transaction_id=transaction_id("bundle-launch"),
        launch_attempt_id=launch_attempt_id("bundle-attempt"),
        expected_version="2.0",
    )
    health = lifecycle.await_health(launch, timeout_sec=20)
    stdout, stderr = processes[0].communicate(timeout=5)

    assert processes[0].returncode == 0, (stdout, stderr)
    assert health.healthy is True
    assert health.launch_attempt_id == launch_attempt_id("bundle-attempt")
    assert health.actual_version == "2.0"
    assert health.executable_path == installed.python
