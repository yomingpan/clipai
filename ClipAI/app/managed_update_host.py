from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from ClipAI.core.managed_update import FailureCode, LaunchAttemptId
from ClipAI.core.managed_update_commands import HostManagedCommand
from ClipAI.core.update_artifacts import UpdateRequestArtifact, UpdateResultArtifact
from ClipAI.core.update_ports import CandidateEnvironmentBuilder
from ClipAI.platform.managed_install import DocumentVerifier, ManagedInstallLayout
from ClipAI.platform.managed_process import ManagedProcessIdentityError, WindowsManagedProcessHandle
from ClipAI.platform.managed_update_backend import FilesystemManagedUpdateBackend
from ClipAI.platform.managed_update_fs import canonical_path
from ClipAI.platform.managed_update_lifecycle import StartProcess, SubprocessManagedApplicationLifecycle
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.update_journal import JsonUpdateTransactionJournal
from ClipAI.services.update_transaction import ManagedUpdateTransaction


class RetainedProcessHandle(Protocol):
    def wait_for_exit(self, *, timeout_sec: float) -> None: ...

    def close(self) -> None: ...


ProcessHandleFactory = Callable[..., RetainedProcessHandle]


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
            lifecycle_arguments = {
                "layout": layout,
                "environment": self._environment,
                "shutdown": lambda _transaction_id: installed_process.wait_for_exit(
                    timeout_sec=self._shutdown_timeout_sec,
                ),
                "now": self._now,
            }
            if self._start_process is not None:
                lifecycle_arguments["start_process"] = self._start_process
            lifecycle = SubprocessManagedApplicationLifecycle(**lifecycle_arguments)  # type: ignore[arg-type]
            transaction = ManagedUpdateTransaction(
                backend=backend,
                lifecycle=lifecycle,
                journal=JsonUpdateTransactionJournal(
                    shared_root=command.shared_root,
                    transaction_id=command.transaction_id,
                ),
                launch_attempt_factory=self._launch_attempt_factory,
                now=self._now,
                health_timeout_sec=self._health_timeout_sec,
            )
            result = transaction.execute(artifact)
            store.write(result)
            return 0 if result.outcome == "updated" else 1
        finally:
            installed_process.close()
