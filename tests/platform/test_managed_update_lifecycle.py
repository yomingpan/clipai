from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, launch_attempt_id, transaction_id
from ClipAI.core.update_artifacts import StartupHealthArtifact
from ClipAI.platform.managed_update_fs import atomic_write_json, native_path
from ClipAI.platform.managed_update_lifecycle import StartupHealthReporter, SubprocessManagedApplicationLifecycle
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore


NOW = "2026-09-13T00:00:00+00:00"


class Layout:
    def __init__(self, tmp_path: Path) -> None:
        self.install_root = (tmp_path / "install").resolve()
        self.shared_root = (tmp_path / "shared").resolve()

    def version_root(self, version: str) -> Path:
        return self.install_root / "versions" / version


class Process:
    pid = 321


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
    assert command[:3] == [str(native_path(python)), "-I", str(native_path(entrypoint))]
    assert command[3:] == [
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
