from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import (
    FailureCode,
    ManagedUpdateFailure,
    TransactionPhase,
    launch_attempt_id,
    transaction_id,
)
from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.core.update_signing import TEST_KEY_ID
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.managed_install import ManagedInstallLayout
from ClipAI.platform.managed_installer import FilesystemManagedInstaller
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner
from ClipAI.platform.managed_release_source import HttpsManagedReleaseSource
from ClipAI.platform.managed_update_backend import FilesystemManagedUpdateBackend
from ClipAI.platform.managed_update_fs import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_verified_chunks,
    file_sha256,
    native_path,
    read_bytes,
    remove_tree,
    regular_file_inventory,
)
from ClipAI.platform.managed_update_lifecycle import SubprocessManagedApplicationLifecycle
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.update_journal import JsonUpdateTransactionJournal
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
from ClipAI.services.managed_update_coordinator import ManagedUpdateCoordinator
from ClipAI.services.update_transaction import ManagedUpdateTransaction


class _Lease:
    def close(self) -> None:
        return


class _Gate:
    def acquire(self) -> _Lease:
        return _Lease()


@dataclass(frozen=True)
class _SigningFixture:
    signer: OpenSshManifestSigner
    verifier: Ed25519ManifestVerifier
    keyring: Path


class _FileReleaseTransport:
    def __init__(self, catalog: bytes, bundle: Path) -> None:
        self._catalog = catalog
        self._bundle = bundle

    def fetch_catalog(self, url: str) -> bytes:
        assert url == "https://updates.invalid/catalog.json"
        return self._catalog

    def download_bundle(
        self,
        url: str,
        destination: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> Path:
        assert url == "https://updates.invalid/clipai-2.0.zip"
        return atomic_write_verified_chunks(
            destination,
            [read_bytes(self._bundle)],
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            maximum_size=expected_size,
        )


class _ProcessHarness:
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []
        self.launched_versions: list[str] = []

    def start(self, arguments, environment, cwd):
        values = list(arguments)
        self.launched_versions.append(values[values.index("--expected-version") + 1])
        process = subprocess.Popen(
            values,
            cwd=native_path(cwd),
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.processes.append(process)
        return process

    def reap(self) -> None:
        for process in self.processes:
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0, (stdout, stderr)


class _FaultingBackend:
    def __init__(self, delegate, failure: str | None, events: list[str]) -> None:
        self._delegate = delegate
        self._failure = failure
        self._events = events

    def _before(self, phase: str) -> None:
        self._events.append(phase)
        if self._failure == phase:
            raise RuntimeError(f"injected {phase} failure")

    def verify(self, request) -> None:
        self._before("verify")
        self._delegate.verify(request)

    def prepare(self, request):
        self._before("prepare")
        return self._delegate.prepare(request)

    def known_good_root(self, request):
        return self._delegate.known_good_root(request)

    def commit(self, candidate):
        self._before("commit")
        return self._delegate.commit(candidate)

    def rollback(self, receipt) -> None:
        self._events.append("rollback")
        self._delegate.rollback(receipt)

    def finalize(self, receipt) -> None:
        self._before("finalize")
        self._delegate.finalize(receipt)


class _FaultingLifecycle:
    def __init__(
        self,
        delegate: SubprocessManagedApplicationLifecycle,
        failure: str | None,
        events: list[str],
        old_root: Path,
    ) -> None:
        self._delegate = delegate
        self._failure = failure
        self._events = events
        self._old_root = old_root

    def request_shutdown(self, transaction_id) -> None:
        self._events.append("shutdown")
        if self._failure == "shutdown":
            raise RuntimeError("injected shutdown failure")
        self._delegate.request_shutdown(transaction_id)

    def launch(self, *, version_root, transaction_id, launch_attempt_id, expected_version):
        self._events.append(f"launch:{expected_version}")
        if self._failure == "launch" and expected_version == "2.0":
            raise RuntimeError("injected launch failure")
        return self._delegate.launch(
            version_root=version_root,
            transaction_id=transaction_id,
            launch_attempt_id=launch_attempt_id,
            expected_version=expected_version,
        )

    def await_health(self, launch, *, timeout_sec):
        self._events.append(f"health:{launch.expected_version}")
        assert native_path(self._old_root).is_dir(), "known-good v1 was removed before health"
        health = self._delegate.await_health(launch, timeout_sec=timeout_sec)
        if self._failure == "health" and launch.expected_version == "2.0":
            raise RuntimeError("injected health failure")
        return health

    def stop(self, launch, *, timeout_sec):
        self._events.append(f"stop:{launch.expected_version}")
        self._delegate.stop(launch, timeout_sec=timeout_sec)


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


def _build_fixture_wheel(
    release_root: Path,
    base_python: Path,
    version: str,
) -> tuple[Path, str]:
    source = release_root / "wheel-source"
    package = source / "src" / "clipai_smoke"
    package.mkdir(parents=True)
    atomic_write_bytes(package / "__init__.py", b"SMOKE = True\n")
    atomic_write_bytes(source / "pyproject.toml", textwrap.dedent("""
        [build-system]
        requires = ["setuptools>=68", "wheel"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "clipai"
        version = "{version}"
        requires-python = ">=3.12,<3.13"

        [tool.setuptools.packages.find]
        where = ["src"]
        """).format(version=version).lstrip().encode("utf-8"))
    wheelhouse = release_root / "wheelhouse"
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


def _signing_fixture(tmp_path: Path) -> _SigningFixture:
    ssh_keygen = shutil.which("ssh-keygen")
    assert ssh_keygen is not None, "Windows OpenSSH ssh-keygen is required"
    root = tmp_path / "signing"
    root.mkdir()
    private_key = root / "fixture-key"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
        capture_output=True,
    )
    signer = OpenSshManifestSigner(
        ssh_keygen=ssh_keygen,
        private_key=private_key,
        work_root=root / "sign-work",
        environment=_clean_environment(),
    )
    public_key = private_key.with_suffix(".pub").read_text(encoding="ascii")
    verifier = Ed25519ManifestVerifier(
        ssh_keygen=ssh_keygen,
        trusted_keys={TEST_KEY_ID: public_key},
        work_root=root / "verify-work",
        environment=_clean_environment(),
        allow_test_keys=True,
    )
    keyring = root / "trusted-keys.json"
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
    return _SigningFixture(signer, verifier, keyring)


def _signed_bundle(
    release_root: Path,
    base_python: Path,
    version: str,
    signing: _SigningFixture,
):
    wheelhouse, wheel_hash = _build_fixture_wheel(
        release_root,
        base_python,
        version,
    )
    payload = release_root / "payload"
    payload.mkdir()
    atomic_write_bytes(payload / "main.py", _health_entrypoint())
    requirements_lock = release_root / "requirements.lock"
    atomic_write_bytes(
        requirements_lock,
        f"clipai=={version} --hash=sha256:{wheel_hash}\n".encode("ascii"),
    )
    return ManagedReleaseBuilder(signing.signer).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=requirements_lock,
        output_path=release_root / f"clipai-{version}.zip",
        app_version=version,
        entrypoint="payload/main.py",
        python_requires=">=3.12,<3.13",
        key_id=TEST_KEY_ID,
    )


def _poisoned_environment(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "VIRTUAL_ENV": "parent-venv",
        "PYTHONPATH": "parent-imports",
        "PYTHONHOME": "parent-home",
        "PIP_CONFIG_FILE": str(tmp_path / "machine-pip.ini"),
        "PIP_INDEX_URL": "https://network.invalid/simple",
        "PIP_EXTRA_INDEX_URL": "https://network.invalid/extra",
        "CLIPAI_INSTANCE_NAME": "managed-bundle-smoke",
    }


def _install_initial(
    *,
    built,
    signing: _SigningFixture,
    base_python: Path,
    install_root: Path,
    shared_root: Path,
    environment: dict[str, str],
):
    installer = FilesystemManagedInstaller(
        manifest_verifier=signing.verifier,
        candidate_builder=OfflineCandidateEnvironmentBuilder(
            environment=environment,
            timeout_sec=120,
        ),
        trusted_keyring_path=signing.keyring,
        update_gate_factory=lambda _root: _Gate(),
    )
    return installer.install(InstallManagedCommand(
        shared_root=shared_root,
        install_root=install_root,
        transaction_id=transaction_id("bundle-install"),
        expected_version="1.0",
        bundle_path=built.bundle_path,
        bundle_size=built.bundle_size,
        bundle_sha256=built.bundle_sha256,
        manifest_sha256=built.manifest_sha256,
        key_id=TEST_KEY_ID,
        managed_install_id="managed-bundle-smoke",
        launcher_version="1.0",
        base_python=base_python,
    ))


def _prepare_update_request(
    *,
    layout: ManagedInstallLayout,
    built,
    transaction: str,
):
    catalog = json.dumps({
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": [{
            "version": "2.0",
            "bundle_url": "https://updates.invalid/clipai-2.0.zip",
            "bundle_sha256": built.bundle_sha256,
            "bundle_size": built.bundle_size,
            "manifest_sha256": built.manifest_sha256,
            "key_id": TEST_KEY_ID,
            "minimum_launcher_version": "1.0",
        }],
    }).encode("utf-8")
    source = HttpsManagedReleaseSource(
        catalog_url="https://updates.invalid/catalog.json",
        transport=_FileReleaseTransport(catalog, built.bundle_path),
    )
    current = layout.prove_current_install()
    identity = ManagedUpdateClientIdentity(
        installed_version=current.version,
        launcher_version="1.0",
        installed_executable=current.python,
        installed_process_id=4242,
        install_root=layout.install_root,
        shared_root=layout.shared_root,
        managed_install_id="managed-bundle-smoke",
    )
    tid = transaction_id(transaction)
    request = ManagedUpdateCoordinator(
        release_source=source,
        now=lambda: "2026-09-13T00:00:00+00:00",
    ).prepare(identity, tid)
    assert request is not None
    ManagedUpdateArtifactStore(
        shared_root=layout.shared_root,
        transaction_id=transaction,
    ).write(request)
    return request


def _transaction_components(
    *,
    layout: ManagedInstallLayout,
    signing: _SigningFixture,
    base_python: Path,
    environment: dict[str, str],
    failure: str | None,
    events: list[str],
):
    backend = FilesystemManagedUpdateBackend(
        layout=layout,
        manifest_verifier=signing.verifier,
        candidate_builder=OfflineCandidateEnvironmentBuilder(
            environment=environment,
            timeout_sec=120,
        ),
        base_python=base_python,
        now=lambda: "2026-09-13T00:00:00+00:00",
    )
    processes = _ProcessHarness()
    lifecycle = SubprocessManagedApplicationLifecycle(
        layout=layout,
        environment=environment,
        shutdown=lambda _transaction_id: None,
        now=lambda: "2026-09-13T00:00:00+00:00",
        start_process=processes.start,
    )
    return (
        _FaultingBackend(backend, failure, events),
        _FaultingLifecycle(
            lifecycle,
            failure,
            events,
            layout.version_root("1.0"),
        ),
        processes,
    )


@pytest.mark.integration
def test_real_managed_bundle_builds_offline_and_launches_identity_bound_health(tmp_path: Path) -> None:
    base_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    signing = _signing_fixture(tmp_path)
    built = _signed_bundle(tmp_path / "release-2.0", base_python, "2.0", signing)
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
        manifest_verifier=signing.verifier,
        candidate_builder=OfflineCandidateEnvironmentBuilder(
            environment=poisoned_environment,
            timeout_sec=120,
        ),
        trusted_keyring_path=signing.keyring,
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
        manifest_verifier=signing.verifier,
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


@pytest.mark.integration
def test_transaction_fault_matrix_preserves_user_data_then_happy_path_finalizes(
    tmp_path: Path,
) -> None:
    base_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    signing = _signing_fixture(tmp_path)
    release_v1 = _signed_bundle(
        tmp_path / "release-1.0",
        base_python,
        "1.0",
        signing,
    )
    release_v2 = _signed_bundle(
        tmp_path / "release-2.0",
        base_python,
        "2.0",
        signing,
    )
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    environment = _poisoned_environment(tmp_path)
    protected = {
        shared_root / "config" / "app.yml": b"provider: user-owned\n",
        shared_root / "state" / "history.json": b'{"items":["keep-me"]}\n',
    }
    for path, content in protected.items():
        atomic_write_bytes(path, content)
    installed_v1 = _install_initial(
        built=release_v1,
        signing=signing,
        base_python=base_python,
        install_root=install_root,
        shared_root=shared_root,
        environment=environment,
    )
    layout = ManagedInstallLayout(
        install_root=install_root,
        shared_root=shared_root,
        manifest_verifier=signing.verifier,
    )
    assert layout.prove_current_install() == installed_v1

    failures = (
        ("verify", FailureCode.BUNDLE_INVALID, "failed"),
        ("prepare", FailureCode.PREPARE_FAILED, "failed"),
        ("shutdown", FailureCode.SHUTDOWN_FAILED, "failed"),
        ("commit", FailureCode.COMMIT_FAILED, "rolled_back"),
        ("launch", FailureCode.LAUNCH_FAILED, "rolled_back"),
        ("health", FailureCode.HEALTH_FAILED, "rolled_back"),
        ("finalize", FailureCode.INTERNAL_ERROR, "rolled_back"),
    )
    for index, (failure, failure_code, outcome) in enumerate(failures, start=1):
        name = f"fault-{index}-{failure}"
        request = _prepare_update_request(
            layout=layout,
            built=release_v2,
            transaction=name,
        )
        events: list[str] = []
        backend, lifecycle, processes = _transaction_components(
            layout=layout,
            signing=signing,
            base_python=base_python,
            environment=environment,
            failure=failure,
            events=events,
        )
        attempt_number = [0]

        def next_attempt():
            attempt_number[0] += 1
            return launch_attempt_id(f"{name}-attempt-{attempt_number[0]}")

        journal = JsonUpdateTransactionJournal(
            shared_root=shared_root,
            transaction_id=request.transaction_id,
        )
        result = ManagedUpdateTransaction(
            backend=backend,
            lifecycle=lifecycle,
            journal=journal,
            launch_attempt_factory=next_attempt,
            now=lambda: "2026-09-13T00:00:00+00:00",
            health_timeout_sec=20,
        ).execute(request)
        ManagedUpdateArtifactStore(
            shared_root=shared_root,
            transaction_id=name,
        ).write(result)
        processes.reap()

        assert (result.outcome, result.active_version, result.failure_code) == (
            outcome,
            "1.0",
            failure_code,
        )
        assert layout.read_state().current_version == "1.0"
        assert layout.prove_current_install().version == "1.0"
        assert native_path(layout.version_root("1.0")).is_dir()
        assert {path: read_bytes(path) for path in protected} == protected
        if failure in {"commit", "launch", "health", "finalize"}:
            assert "1.0" in processes.launched_versions
        if failure in {"health", "finalize"}:
            assert events.index("rollback") < events.index("stop:2.0")
            assert events.index("stop:2.0") < events.index("launch:1.0")

        target = layout.version_root("2.0")
        if native_path(target).exists():
            remove_tree(target)

    request = _prepare_update_request(
        layout=layout,
        built=release_v2,
        transaction="happy-update",
    )
    events: list[str] = []
    backend, lifecycle, processes = _transaction_components(
        layout=layout,
        signing=signing,
        base_python=base_python,
        environment=environment,
        failure=None,
        events=events,
    )
    journal = JsonUpdateTransactionJournal(
        shared_root=shared_root,
        transaction_id=request.transaction_id,
    )
    result = ManagedUpdateTransaction(
        backend=backend,
        lifecycle=lifecycle,
        journal=journal,
        launch_attempt_factory=lambda: launch_attempt_id("happy-attempt"),
        now=lambda: "2026-09-13T00:00:00+00:00",
        health_timeout_sec=20,
    ).execute(request)
    store = ManagedUpdateArtifactStore(
        shared_root=shared_root,
        transaction_id="happy-update",
    )
    store.write(result)
    processes.reap()

    assert (result.outcome, result.active_version, result.failure_code) == (
        "updated",
        "2.0",
        None,
    )
    assert processes.launched_versions == ["2.0"]
    assert events == [
        "verify",
        "prepare",
        "shutdown",
        "commit",
        "launch:2.0",
        "health:2.0",
        "finalize",
    ]
    state = layout.read_state()
    assert (state.current_version, state.previous_version) == ("2.0", "1.0")
    assert layout.prove_current_install().version == "2.0"
    assert native_path(layout.version_root("1.0")).is_dir()
    assert native_path(layout.version_root("2.0")).is_dir()
    assert {path: read_bytes(path) for path in protected} == protected
    _revision, snapshot = journal.read()
    assert snapshot.phase is TransactionPhase.FINALIZE
    assert store.read("result") == result
