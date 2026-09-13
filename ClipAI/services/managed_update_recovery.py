from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_update import FailureCode, LaunchAttemptId, TransactionPhase, TransactionSnapshot
from ClipAI.core.update_artifacts import UpdateRequestArtifact, UpdateResultArtifact, validate_health_relation
from ClipAI.core.update_ports import ManagedApplicationLifecycle, ManagedUpdateRecoveryBackend, UpdateTransactionJournal


class ManagedUpdateRecovery:
    """Conservatively restore and prove the installed version after interruption."""

    def __init__(
        self,
        *,
        backend: ManagedUpdateRecoveryBackend,
        lifecycle: ManagedApplicationLifecycle,
        journal: UpdateTransactionJournal,
        launch_attempt_factory: Callable[[], LaunchAttemptId],
        now: Callable[[], str],
        health_timeout_sec: float = 20.0,
    ) -> None:
        if health_timeout_sec <= 0:
            raise ValueError("managed recovery health budget must be positive")
        self._backend = backend
        self._lifecycle = lifecycle
        self._journal = journal
        self._launch_attempt_factory = launch_attempt_factory
        self._now = now
        self._health_timeout_sec = health_timeout_sec

    def execute(
        self,
        request: UpdateRequestArtifact,
        interrupted: TransactionSnapshot,
    ) -> UpdateResultArtifact:
        failure = FailureCode.UPDATE_INTERRUPTED
        try:
            self._validate_identity(request, interrupted)
            self._journal.record(TransactionSnapshot(
                request.transaction_id,
                TransactionPhase.ROLLBACK,
                request.installed_version,
                request.target_version,
                failure,
            ))
            known_good = self._backend.restore_known_good(request)
            launch = self._lifecycle.launch(
                version_root=known_good.root,
                transaction_id=request.transaction_id,
                launch_attempt_id=self._launch_attempt_factory(),
                expected_version=request.installed_version,
            )
            health = self._lifecycle.await_health(
                launch,
                timeout_sec=self._health_timeout_sec,
            )
            validate_health_relation(launch, health)
            return UpdateResultArtifact(
                request.transaction_id,
                self._now(),
                "rolled_back",
                request.installed_version,
                failure,
            )
        except Exception:
            return UpdateResultArtifact(
                request.transaction_id,
                self._now(),
                "failed",
                request.installed_version,
                failure,
                FailureCode.ROLLBACK_FAILED,
            )

    @staticmethod
    def _validate_identity(
        request: UpdateRequestArtifact,
        interrupted: TransactionSnapshot,
    ) -> None:
        if (
            interrupted.transaction_id != request.transaction_id
            or interrupted.installed_version != request.installed_version
            or interrupted.target_version != request.target_version
        ):
            raise ValueError("recovery journal identity does not match request")
