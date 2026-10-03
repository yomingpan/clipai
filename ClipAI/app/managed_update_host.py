from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from ClipAI.core.managed_update import FailureCode, LaunchAttemptId, TransactionId
from ClipAI.core.managed_update_commands import HostManagedCommand
from ClipAI.core.update_artifacts import UpdateRequestArtifact, UpdateResultArtifact
from ClipAI.core.update_ports import CandidateEnvironmentBuilder, ManagedUpdateGate
from ClipAI.platform.managed_install import DocumentVerifier, ManagedInstallLayout
from ClipAI.platform.managed_process import ManagedProcessIdentityError, WindowsManagedProcessHandle
from ClipAI.platform.managed_update_backend import FilesystemManagedUpdateBackend
from ClipAI.platform.managed_update_fs import canonical_path, native_path
from ClipAI.platform.managed_update_lifecycle import StartProcess, SubprocessManagedApplicationLifecycle
from ClipAI.platform.managed_update_mutex import WindowsManagedUpdateGate
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.update_journal import JsonUpdateTransactionJournal
from ClipAI.services.managed_update_recovery import ManagedUpdateRecovery
from ClipAI.services.update_transaction import ManagedUpdateTransaction


class RetainedProcessHandle(Protocol):
    def wait_for_exit(self, *, timeout_sec: float) -> None: ...

    def close(self) -> None: ...


ProcessHandleFactory = Callable[..., RetainedProcessHandle]
UpdateGateFactory = Callable[[Path], ManagedUpdateGate]


class ManagedUpdateHostExecutor:
    """Compose and execute one external managed-update host transaction."""

    def __init__(
        self,
        *,
        manifest_verifier: DocumentVerifier,
        candidate_builder: CandidateEnvironmentBuilder,
        environment: Mapping[str, str],
        now: Callable[[], str],
        launch_attempt_factory: Callable[[], LaunchAttemptId],
        process_handle_factory: ProcessHandleFactory = WindowsManagedProcessHandle,
        update_gate_factory: UpdateGateFactory = WindowsManagedUpdateGate,
        start_process: StartProcess | None = None,
        shutdown_timeout_sec: float = 20.0,
        health_timeout_sec: float = 20.0,
    ) -> None:
        self._manifest_verifier = manifest_verifier
        self._candidate_builder = candidate_builder
        self._environment = dict(environment)
        self._now = now
        self._launch_attempt_factory = launch_attempt_factory
        self._process_handle_factory = process_handle_factory
        self._update_gate_factory = update_gate_factory
        self._start_process = start_process
        self._shutdown_timeout_sec = shutdown_timeout_sec
        self._health_timeout_sec = health_timeout_sec

    def execute(self, command: HostManagedCommand) -> int:
        store = ManagedUpdateArtifactStore(
            shared_root=command.shared_root,
            transaction_id=str(command.transaction_id),
        )
        artifact = store.read("request")
        if not isinstance(artifact, UpdateRequestArtifact):
            raise ValueError("managed update request artifact has wrong type")
        if (
            artifact.transaction_id != command.transaction_id
            or canonical_path(artifact.shared_root) != canonical_path(command.shared_root)
            or canonical_path(artifact.install_root) != canonical_path(command.install_root)
        ):
            raise ValueError("managed update host command does not match request")

        lease = self._update_gate_factory(command.install_root).acquire()
        if lease is None:
            store.write(UpdateResultArtifact(
                artifact.transaction_id,
                self._now(),
                "failed",
                artifact.installed_version,
                FailureCode.UPDATE_BUSY,
            ))
            return 1
        try:
            if native_path(store.path("result")).is_file():
                terminal = store.read("result")
                if not isinstance(terminal, UpdateResultArtifact):
                    raise ValueError("managed update result artifact has wrong type")
                return 0 if terminal.outcome == "updated" else 1

            layout = ManagedInstallLayout(
                install_root=command.install_root,
                shared_root=command.shared_root,
                manifest_verifier=self._manifest_verifier,
            )
            backend = FilesystemManagedUpdateBackend(
                layout=layout,
                manifest_verifier=self._manifest_verifier,
                candidate_builder=self._candidate_builder,
                base_python=command.base_python,
                now=self._now,
            )
            journal = JsonUpdateTransactionJournal(
                shared_root=command.shared_root,
                transaction_id=command.transaction_id,
            )
            if native_path(journal.path).is_file():
                _revision, interrupted = journal.read()
                recovery = ManagedUpdateRecovery(
                    backend=backend,
                    lifecycle=self._lifecycle(layout, lambda _transaction_id: None),
                    journal=journal,
                    launch_attempt_factory=self._launch_attempt_factory,
                    now=self._now,
                    health_timeout_sec=self._health_timeout_sec,
                )
                result = recovery.execute(artifact, interrupted)
                store.write(result)
                return 1

            try:
                installed_process = self._process_handle_factory(
                    process_id=artifact.installed_process_id,
                    expected_executable=artifact.installed_executable,
                )
            except ManagedProcessIdentityError:
                store.write(UpdateResultArtifact(
                    artifact.transaction_id,
                    self._now(),
                    "failed",
                    artifact.installed_version,
                    FailureCode.IDENTITY_INELIGIBLE,
                ))
                return 1
            try:
                lifecycle = self._lifecycle(
                    layout,
                    lambda _transaction_id: installed_process.wait_for_exit(
                        timeout_sec=self._shutdown_timeout_sec,
                    ),
                )
                transaction = ManagedUpdateTransaction(
                    backend=backend,
                    lifecycle=lifecycle,
                    journal=journal,
                    launch_attempt_factory=self._launch_attempt_factory,
                    now=self._now,
                    health_timeout_sec=self._health_timeout_sec,
                    stop_timeout_sec=self._shutdown_timeout_sec,
                )
                result = transaction.execute(artifact)
                store.write(result)
                return 0 if result.outcome == "updated" else 1
            finally:
                installed_process.close()
        finally:
            lease.close()

    def _lifecycle(
        self,
        layout: ManagedInstallLayout,
        shutdown: Callable[[TransactionId], None],
    ) -> SubprocessManagedApplicationLifecycle:
        if self._start_process is None:
            return SubprocessManagedApplicationLifecycle(
                layout=layout,
                environment=self._environment,
                shutdown=shutdown,
                now=self._now,
            )
        return SubprocessManagedApplicationLifecycle(
            layout=layout,
            environment=self._environment,
            shutdown=shutdown,
            now=self._now,
            start_process=self._start_process,
        )
