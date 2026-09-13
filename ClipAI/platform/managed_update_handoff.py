from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import time
from typing import Protocol

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.update_artifacts import HandoffReadyArtifact, UpdateRequestArtifact, UpdateResultArtifact
from ClipAI.platform.managed_update_fs import canonical_path, native_path
from ClipAI.platform.managed_update_lifecycle import isolated_managed_environment, start_detached_process
from ClipAI.platform.update_artifacts import ArtifactValidationError, ManagedUpdateArtifactStore


class HostProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...


StartHostProcess = Callable[[Sequence[str], Mapping[str, str], Path], HostProcess]


class SubprocessManagedUpdateHandoff:
    """Publish one request and await exact preparation evidence from a stable host."""

    def __init__(
        self,
        *,
        launcher_python: str | Path,
        launcher_entrypoint: str | Path,
        base_python: str | Path,
        environment: Mapping[str, str],
        start_process: StartHostProcess = start_detached_process,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout_sec: float = 20.0,
        poll_interval_sec: float = 0.05,
    ) -> None:
        if timeout_sec <= 0 or poll_interval_sec <= 0:
            raise ValueError("managed update handoff budgets must be positive")
        self._launcher_python = canonical_path(launcher_python)
        self._launcher_entrypoint = canonical_path(launcher_entrypoint)
        self._base_python = canonical_path(base_python)
        self._environment = isolated_managed_environment(environment)
        self._start_process = start_process
        self._monotonic = monotonic
        self._sleep = sleep
        self._timeout_sec = timeout_sec
        self._poll_interval_sec = poll_interval_sec

    def prepare(self, request: UpdateRequestArtifact) -> HandoffReadyArtifact:
        store = ManagedUpdateArtifactStore(
            shared_root=request.shared_root,
            transaction_id=str(request.transaction_id),
        )
        try:
            self._validate_runtime_files()
            store.write(request)
            process = self._start_process(
                self._command(request),
                self._environment,
                self._launcher_entrypoint.parent,
            )
            if isinstance(process.pid, bool) or not isinstance(process.pid, int) or process.pid <= 0:
                raise ValueError("host returned invalid process identity")
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.HANDOFF_FAILED, "managed update host did not start") from exc

        deadline = self._monotonic() + self._timeout_sec
        while self._monotonic() < deadline:
            if native_path(store.path("result")).is_file():
                self._raise_terminal_result(store, request)
            if native_path(store.path("handoff_ready")).is_file():
                return self._read_readiness(store, request)
            if process.poll() is not None:
                raise ManagedUpdateFailure(FailureCode.HANDOFF_FAILED, "managed update host exited before readiness")
            self._sleep(self._poll_interval_sec)
        raise ManagedUpdateFailure(FailureCode.HANDOFF_TIMEOUT, "managed update handoff timed out")

    def _validate_runtime_files(self) -> None:
        if not all(native_path(path).is_file() for path in (
            self._launcher_python, self._launcher_entrypoint, self._base_python,
        )):
            raise ValueError("stable launcher runtime is incomplete")

    def _command(self, request: UpdateRequestArtifact) -> list[str]:
        return [
            str(self._launcher_python), "-I", str(self._launcher_entrypoint), "host",
            "--shared-root", str(request.shared_root),
            "--transaction-id", str(request.transaction_id),
            "--install-root", str(request.install_root),
            "--base-python", str(self._base_python),
        ]

    def _raise_terminal_result(
        self,
        store: ManagedUpdateArtifactStore,
        request: UpdateRequestArtifact,
    ) -> None:
        try:
            result = store.read("result")
            if not isinstance(result, UpdateResultArtifact):
                raise ArtifactValidationError("managed update result type is invalid")
            code = result.failure_code or FailureCode.HANDOFF_FAILED
        except (ArtifactValidationError, OSError, ValueError) as exc:
            raise ManagedUpdateFailure(FailureCode.HANDOFF_FAILED, "managed update result is invalid") from exc
        raise ManagedUpdateFailure(code, "managed update host failed before readiness")

    def _read_readiness(
        self,
        store: ManagedUpdateArtifactStore,
        request: UpdateRequestArtifact,
    ) -> HandoffReadyArtifact:
        try:
            ready = store.read("handoff_ready")
            if not isinstance(ready, HandoffReadyArtifact):
                raise ArtifactValidationError("managed update readiness type is invalid")
            expected_root = canonical_path(request.install_root / "versions" / request.target_version)
            expected_python = canonical_path(expected_root / ".venv" / "Scripts" / "python.exe")
            if (
                ready.transaction_id != request.transaction_id
                or ready.expected_version != request.target_version
                or ready.manifest_sha256 != request.manifest_sha256
                or canonical_path(ready.candidate_root) != expected_root
                or canonical_path(ready.candidate_python) != expected_python
            ):
                raise ArtifactValidationError("managed update readiness does not match request")
            return ready
        except (ArtifactValidationError, OSError, ValueError) as exc:
            raise ManagedUpdateFailure(FailureCode.HANDOFF_FAILED, "managed update readiness is invalid") from exc
