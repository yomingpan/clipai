from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, TransactionPhase, TransactionSnapshot, launch_attempt_id, transaction_id
from ClipAI.core.update_artifacts import StartupHealthArtifact, UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_update_fs import atomic_write_json, native_path
from ClipAI.platform.managed_update_lifecycle import StartupHealthReporter, SubprocessManagedApplicationLifecycle
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.managed_update_lifecycle import start_detached_process
from ClipAI.services.managed_current_launch import ManagedCurrentLaunchCoordinator
from ClipAI.services.managed_update_recovery import ManagedUpdateRecovery


NOW = "2026-09-13T00:00:00+00:00"


def test_desktop_launch_uses_no_window_without_detached_console(monkeypatch, tmp_path: Path):
    captured = {}
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(subprocess, "DETACHED_PROCESS", 8, raising=False)

    def popen(command, **kwargs):
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr(subprocess, "Popen", popen)
    start_detached_process(["private-python.exe", "-I", "main.py"], {}, tmp_path)
    assert captured["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert not captured["creationflags"] & subprocess.DETACHED_PROCESS


class Layout:
    def __init__(self, tmp_path: Path) -> None:
        self.install_root = (tmp_path / "install").resolve()
        self.shared_root = (tmp_path / "shared").resolve()

    def version_root(self, version: str) -> Path:
        return self.install_root / "versions" / version


class Process:
    def __init__(self) -> None:
        self.pid = 321
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.returncode = 0
        return self.returncode


def _installed_version(layout: Layout, version: str = "2.0") -> tuple[Path, Path]:
    root = layout.version_root(version)
    python = root / ".venv" / "Scripts" / "python.exe"
    entrypoint = root / "payload" / "main.py"
    python.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    python.write_bytes(b"")
    entrypoint.write_text("print('managed')\n", encoding="utf-8")
    atomic_write_json(root / "install-manifest.json", {
        "schema_version": 1,
        "app_version": version,
        "bundle_format": "clipai-managed-v1",
        "entrypoint": "payload/main.py",
        "python_requires": ">=3.11",
        "requirements_lock_sha256": "a" * 64,
        "files": [
            {"path": "payload/main.py", "size": 17, "sha256": "b" * 64, "role": "payload"},
            {"path": "requirements.lock", "size": 0, "sha256": "a" * 64, "role": "metadata"},
            {"path": "wheelhouse/clipai.whl", "size": 0, "sha256": "c" * 64, "role": "wheel"},
        ],
        "signing_namespace": "clipai.managed-update.manifest.v1",
        "key_id": "release-key",
    })
    return python, entrypoint


def _lifecycle(layout: Layout, *, starter, shutdown=lambda _tid: None, clock=None, sleep=None):
    return SubprocessManagedApplicationLifecycle(
        layout=layout,  # type: ignore[arg-type]
        environment={
            "PATH": "managed-path",
            "PYTHONPATH": "parent-imports",
            "PYTHONHOME": "parent-home",
            "VIRTUAL_ENV": "parent-venv",
            "CLIPAI_INSTANCE_NAME": "update-sandbox",
        },
        shutdown=shutdown,
        now=lambda: NOW,
        start_process=starter,
        monotonic=clock or (lambda: 0.0),
        sleep=sleep or (lambda _seconds: None),
    )


def test_launch_uses_exact_managed_executable_contract_and_isolated_environment(tmp_path: Path):
    layout = Layout(tmp_path)
    python, entrypoint = _installed_version(layout)
    calls = []

    def starter(command, environment, cwd):
        calls.append((list(command), dict(environment), cwd))
        return Process()

    lifecycle = _lifecycle(layout, starter=starter)
    receipt = lifecycle.launch(
        version_root=layout.version_root("2.0"),
        transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("attempt-1"),
        expected_version="2.0",
    )
    command, environment, cwd = calls[0]
    assert command[:4] == [str(python.resolve()), "-I", str(entrypoint.resolve()), "launch"]
    assert command[4:] == [
        "--shared-root", str(layout.shared_root),
        "--transaction-id", "tx-1",
        "--install-root", str(layout.install_root),
        "--launch-attempt-id", "attempt-1",
        "--expected-version", "2.0",
    ]
    assert cwd == layout.version_root("2.0")
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & environment.keys()
    assert environment["CLIPAI_INSTANCE_NAME"] == "update-sandbox"
    assert receipt.executable_path == python and receipt.process_id == 321
    stored = ManagedUpdateArtifactStore(shared_root=layout.shared_root, transaction_id="tx-1").read("launch_receipt")
    assert stored == receipt


def test_health_wait_ignores_stale_attempt_then_accepts_exact_startup_evidence(tmp_path: Path):
    layout = Layout(tmp_path)
    python, _ = _installed_version(layout)
    lifecycle = _lifecycle(layout, starter=lambda *_args: Process())
    launch = lifecycle.launch(
        version_root=layout.version_root("2.0"),
        transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("attempt-1"),
        expected_version="2.0",
    )
    reporter = StartupHealthReporter(shared_root=layout.shared_root, now=lambda: NOW)
    reporter.report(
        transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("stale-attempt"),
        expected_version="2.0",
        actual_version="2.0",
        executable_path=python,
        healthy=True,
    )
    tick = [0.0]

    def sleep(_seconds: float) -> None:
        reporter.report(
            transaction_id=transaction_id("tx-1"),
            launch_attempt_id=launch_attempt_id("attempt-1"),
            expected_version="2.0",
            actual_version="2.0",
            executable_path=python,
            healthy=True,
        )
        tick[0] += 0.05

    lifecycle._monotonic = lambda: tick[0]
    lifecycle._sleep = sleep
    health = lifecycle.await_health(launch, timeout_sec=1.0)
    assert health.launch_attempt_id == launch.launch_attempt_id


def test_matching_attempt_with_wrong_version_fails_and_missing_health_times_out(tmp_path: Path):
    layout = Layout(tmp_path)
    python, _ = _installed_version(layout)
    tick = [0.0]
    lifecycle = _lifecycle(
        layout,
        starter=lambda *_args: Process(),
        clock=lambda: tick[0],
        sleep=lambda seconds: tick.__setitem__(0, tick[0] + seconds),
    )
    launch = lifecycle.launch(
        version_root=layout.version_root("2.0"),
        transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("attempt-1"),
        expected_version="2.0",
    )
    store = ManagedUpdateArtifactStore(shared_root=layout.shared_root, transaction_id="tx-1")
    store.write(StartupHealthArtifact(launch.transaction_id, NOW, launch.launch_attempt_id, "2.0", "1.0", python, True))
    with pytest.raises(ManagedUpdateFailure) as mismatch:
        lifecycle.await_health(launch, timeout_sec=1.0)
    assert mismatch.value.code is FailureCode.HEALTH_FAILED

    store.path("startup_health").unlink()
    with pytest.raises(ManagedUpdateFailure) as timeout:
        lifecycle.await_health(launch, timeout_sec=0.1)
    assert timeout.value.code is FailureCode.HEALTH_TIMEOUT


def test_shutdown_callback_failure_is_typed(tmp_path: Path):
    layout = Layout(tmp_path)

    def fail(_transaction_id):
        raise RuntimeError("still running")

    lifecycle = _lifecycle(layout, starter=lambda *_args: Process(), shutdown=fail)
    with pytest.raises(ManagedUpdateFailure) as raised:
        lifecycle.request_shutdown(transaction_id("tx-1"))
    assert raised.value.code is FailureCode.SHUTDOWN_FAILED


def test_stop_uses_the_exact_owned_launch_identity_and_proves_process_exit(tmp_path: Path):
    layout = Layout(tmp_path)
    _installed_version(layout)
    process = Process()
    lifecycle = _lifecycle(layout, starter=lambda *_args: process)
    launch = lifecycle.launch(
        version_root=layout.version_root("2.0"),
        transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("attempt-1"),
        expected_version="2.0",
    )

    with pytest.raises(ManagedUpdateFailure) as wrong_identity:
        lifecycle.stop(replace(launch, process_id=999), timeout_sec=1.0)
    assert wrong_identity.value.code is FailureCode.SHUTDOWN_FAILED
    assert process.terminated is False

    lifecycle.stop(launch, timeout_sec=1.0)
    assert process.terminated is True
    assert process.poll() == 0


def test_launch_failure_after_process_start_cleans_up_the_unpublished_process(tmp_path: Path):
    layout = Layout(tmp_path)
    _installed_version(layout)
    layout.shared_root.write_text("blocks artifact directory", encoding="utf-8")
    process = Process()
    lifecycle = _lifecycle(layout, starter=lambda *_args: process)

    with pytest.raises(ManagedUpdateFailure) as raised:
        lifecycle.launch(
            version_root=layout.version_root("2.0"),
            transaction_id=transaction_id("tx-1"),
            launch_attempt_id=launch_attempt_id("attempt-1"),
            expected_version="2.0",
        )

    assert raised.value.code is FailureCode.LAUNCH_FAILED
    assert process.terminated is True
    assert process.poll() == 0


@pytest.mark.parametrize("evidence", ["healthy", "wrong-version", "unhealthy", "stale", "missing"])
def test_health_deadline_samples_and_validates_final_evidence_without_oversleep(tmp_path: Path, evidence):
    layout = Layout(tmp_path)
    python, _ = _installed_version(layout)
    tick = [0.0]
    reporter = StartupHealthReporter(shared_root=layout.shared_root, now=lambda: NOW)

    def sleep(seconds):
        tick[0] += seconds
        if tick[0] >= 1.0 and evidence != "missing":
            reporter.report(
                transaction_id=transaction_id("tx-1"),
                launch_attempt_id=launch_attempt_id("stale" if evidence == "stale" else "attempt-1"),
                expected_version="2.0", actual_version="1.0" if evidence == "wrong-version" else "2.0",
                executable_path=python, healthy=evidence != "unhealthy",
            )

    lifecycle = _lifecycle(layout, starter=lambda *_args: Process(), clock=lambda: tick[0], sleep=sleep)
    lifecycle._poll_interval_sec = 0.3
    launch = lifecycle.launch(
        version_root=layout.version_root("2.0"), transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("attempt-1"), expected_version="2.0",
    )
    if evidence == "healthy":
        health = lifecycle.await_health(launch, timeout_sec=1.0)
        assert health.healthy and health.launch_attempt_id == launch.launch_attempt_id
    else:
        with pytest.raises(ManagedUpdateFailure) as raised:
            lifecycle.await_health(launch, timeout_sec=1.0)
        assert raised.value.code is (
            FailureCode.HEALTH_FAILED if evidence in {"wrong-version", "unhealthy"} else FailureCode.HEALTH_TIMEOUT
        )
    assert tick[0] == 1.0


@pytest.mark.parametrize("owner", ["current-launch", "recovery"])
def test_current_and_recovery_defaults_allow_real_30_second_health_wait(tmp_path: Path, owner):
    layout = Layout(tmp_path)
    python, entrypoint = _installed_version(layout)
    candidate = CandidateEnvironment(layout.version_root("2.0"), python, entrypoint, "2.0")
    tick = [0.0]
    reporter = StartupHealthReporter(shared_root=layout.shared_root, now=lambda: NOW)

    def sleep(seconds):
        tick[0] += seconds
        if tick[0] >= 30.0:
            reporter.report(
                transaction_id=transaction_id("tx-1"), launch_attempt_id=launch_attempt_id("attempt-1"),
                expected_version="2.0", actual_version="2.0", executable_path=python, healthy=True,
            )

    lifecycle = _lifecycle(layout, starter=lambda *_args: Process(), clock=lambda: tick[0], sleep=sleep)
    lifecycle._poll_interval_sec = 1.0
    if owner == "current-launch":
        health = ManagedCurrentLaunchCoordinator(
            install=SimpleNamespace(prove_current_install=lambda: candidate), lifecycle=lifecycle,
            transaction_id_factory=lambda: transaction_id("tx-1"),
            launch_attempt_factory=lambda: launch_attempt_id("attempt-1"),
        ).execute()
        assert health.healthy and health.actual_version == "2.0"
    else:
        request = UpdateRequestArtifact(
            transaction_id("tx-1"), NOW, "2.0", "3.0", python, 123,
            (tmp_path / "release.zip").resolve(), 42, "a" * 64, "b" * 64,
            "release-key", layout.install_root, layout.shared_root, "managed-1",
        )
        snapshots = []
        recovery = ManagedUpdateRecovery(
            backend=SimpleNamespace(restore_known_good=lambda _request: candidate), lifecycle=lifecycle,
            journal=SimpleNamespace(record=snapshots.append),
            launch_attempt_factory=lambda: launch_attempt_id("attempt-1"), now=lambda: NOW,
        )
        result = recovery.execute(request, TransactionSnapshot(request.transaction_id, TransactionPhase.HEALTH, "2.0", "3.0"))
        assert (result.outcome, result.active_version, result.failure_code, result.rollback_failure_code) == (
            "rolled_back", "2.0", FailureCode.UPDATE_INTERRUPTED, None,
        )
        assert snapshots[0].phase is TransactionPhase.ROLLBACK
    assert tick[0] == 30.0
