from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
import subprocess
import time
from typing import Protocol

from ClipAI.core.managed_update import FailureCode, LaunchAttemptId, ManagedUpdateFailure, TransactionId
from ClipAI.core.update_artifacts import LaunchReceiptArtifact, StartupHealthArtifact, validate_health_relation
from ClipAI.platform.managed_install import ManagedInstallLayout
from ClipAI.platform.managed_update_fs import canonical_path, native_path, read_json
from ClipAI.platform.update_artifacts import ArtifactValidationError, ManagedUpdateArtifactStore
from ClipAI.platform.update_bundle import parse_install_manifest


class SpawnedProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


StartProcess = Callable[[Sequence[str], Mapping[str, str], Path], SpawnedProcess]


def start_detached_process(command: Sequence[str], environment: Mapping[str, str], cwd: Path) -> SpawnedProcess:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen(
        command,
        cwd=native_path(cwd),
        env=dict(environment),
        close_fds=True,
        creationflags=flags,
    )


class SubprocessManagedApplicationLifecycle:
    def __init__(
        self,
        *,
        layout: ManagedInstallLayout,
        environment: Mapping[str, str],
        shutdown: Callable[[TransactionId], None],
        now: Callable[[], str],
        start_process: StartProcess = start_detached_process,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval_sec: float = 0.05,
    ) -> None:
        self._layout = layout
        self._environment = isolated_managed_environment(environment)
        self._shutdown = shutdown
        self._now = now
        self._start_process = start_process
        self._monotonic = monotonic
        self._sleep = sleep
        self._poll_interval_sec = poll_interval_sec
        self._launched: dict[
            tuple[TransactionId, LaunchAttemptId],
            tuple[LaunchReceiptArtifact, SpawnedProcess],
        ] = {}

    def request_shutdown(self, transaction_id: TransactionId) -> None:
        try:
            self._shutdown(transaction_id)
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.SHUTDOWN_FAILED, "application shutdown did not complete") from exc

    def launch(
        self,
        *,
        version_root: Path,
        transaction_id: TransactionId,
        launch_attempt_id: LaunchAttemptId,
        expected_version: str,
    ) -> LaunchReceiptArtifact:
        process: SpawnedProcess | None = None
        try:
            expected_root = self._layout.version_root(expected_version)
            if version_root.resolve() != expected_root.resolve():
                raise ValueError("launch root does not match expected version")
            manifest = parse_install_manifest(read_json(expected_root / "install-manifest.json"))
            if manifest.app_version != expected_version:
                raise ValueError("launch manifest version does not match")
            python = expected_root / ".venv" / "Scripts" / "python.exe"
            entrypoint = expected_root.joinpath(*PurePosixPath(manifest.entrypoint).parts)
            if not native_path(python).is_file() or not native_path(entrypoint).is_file():
                raise ValueError("launch executable or entrypoint is missing")
            command = [
                str(native_path(python)), "-I", str(native_path(entrypoint)), "launch",
                "--shared-root", str(self._layout.shared_root),
                "--transaction-id", str(transaction_id),
                "--install-root", str(self._layout.install_root),
                "--launch-attempt-id", str(launch_attempt_id),
                "--expected-version", expected_version,
            ]
            process = self._start_process(command, self._environment, expected_root)
            if isinstance(process.pid, bool) or not isinstance(process.pid, int) or process.pid <= 0:
                raise ValueError("launcher returned invalid process identity")
            receipt = LaunchReceiptArtifact(
                transaction_id,
                self._now(),
                launch_attempt_id,
                expected_version,
                canonical_path(python),
                process.pid,
            )
            self._store(transaction_id).write(receipt)
            self._launched[(transaction_id, launch_attempt_id)] = (receipt, process)
            return receipt
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            if process is not None:
                try:
                    _stop_process(process, timeout_sec=1.0)
                except Exception:
                    pass
            raise ManagedUpdateFailure(FailureCode.LAUNCH_FAILED, "managed application launch failed") from exc

    def await_health(self, launch: LaunchReceiptArtifact, *, timeout_sec: float) -> StartupHealthArtifact:
        deadline = self._monotonic() + timeout_sec
        store = self._store(launch.transaction_id)
        while self._monotonic() < deadline:
            if native_path(store.path("startup_health")).is_file():
                try:
                    artifact = store.read("startup_health")
                    if not isinstance(artifact, StartupHealthArtifact):
                        raise ArtifactValidationError("startup health artifact type is invalid")
                    if artifact.launch_attempt_id != launch.launch_attempt_id:
                        self._sleep(self._poll_interval_sec)
                        continue
                    validate_health_relation(launch, artifact)
                    return artifact
                except ArtifactValidationError as exc:
                    raise ManagedUpdateFailure(FailureCode.HEALTH_FAILED, "startup health evidence is invalid") from exc
                except ValueError as exc:
                    raise ManagedUpdateFailure(FailureCode.HEALTH_FAILED, "startup health does not match launch") from exc
            self._sleep(self._poll_interval_sec)
        raise ManagedUpdateFailure(FailureCode.HEALTH_TIMEOUT, "startup health timed out")

    def stop(self, launch: LaunchReceiptArtifact, *, timeout_sec: float) -> None:
        key = (launch.transaction_id, launch.launch_attempt_id)
        owned = self._launched.get(key)
        if owned is None or owned[0] != launch:
            raise ManagedUpdateFailure(
                FailureCode.SHUTDOWN_FAILED,
                "launch process identity is not owned by this lifecycle",
            )
        try:
            _stop_process(owned[1], timeout_sec=timeout_sec)
        except Exception as exc:
            raise ManagedUpdateFailure(
                FailureCode.SHUTDOWN_FAILED,
                "launched application did not stop",
            ) from exc
        del self._launched[key]

    def _store(self, transaction_id: TransactionId) -> ManagedUpdateArtifactStore:
        return ManagedUpdateArtifactStore(shared_root=self._layout.shared_root, transaction_id=str(transaction_id))


class StartupHealthReporter:
    def __init__(self, *, shared_root: str | Path, now: Callable[[], str]) -> None:
        self._shared_root = Path(shared_root).resolve()
        self._now = now

    def report(
        self,
        *,
        transaction_id: TransactionId,
        launch_attempt_id: LaunchAttemptId,
        expected_version: str,
        actual_version: str,
        executable_path: str | Path,
        healthy: bool,
    ) -> StartupHealthArtifact:
        artifact = StartupHealthArtifact(
            transaction_id,
            self._now(),
            launch_attempt_id,
            expected_version,
            actual_version,
            canonical_path(executable_path),
            healthy,
        )
        ManagedUpdateArtifactStore(
            shared_root=self._shared_root,
            transaction_id=str(transaction_id),
        ).write(artifact)
        return artifact


def isolated_managed_environment(environment: Mapping[str, str]) -> dict[str, str]:
    blocked = {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"}
    isolated = {key: value for key, value in environment.items() if key.upper() not in blocked}
    isolated["PYTHONNOUSERSITE"] = "1"
    return isolated


def _stop_process(process: SpawnedProcess, *, timeout_sec: float) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=max(timeout_sec, 0.0))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=max(timeout_sec, 1.0))
    if process.poll() is None:
        raise RuntimeError("process remained active after termination")
