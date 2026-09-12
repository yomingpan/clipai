from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_update import (
    CommitReceipt,
    FailureCode,
    LaunchAttemptId,
    ManagedUpdateFailure,
    TransactionPhase,
    TransactionSnapshot,
)
from ClipAI.core.update_artifacts import UpdateRequestArtifact, UpdateResultArtifact, validate_health_relation
from ClipAI.core.update_ports import ManagedApplicationLifecycle, ManagedUpdateBackend, UpdateTransactionJournal


class ManagedUpdateTransaction:
    """Own the legal transaction sequence and rollback decision."""

    def __init__(self, *, backend: ManagedUpdateBackend, lifecycle: ManagedApplicationLifecycle, journal: UpdateTransactionJournal, launch_attempt_factory: Callable[[], LaunchAttemptId], now: Callable[[], str], health_timeout_sec: float = 20.0) -> None:
        self._backend = backend
        self._lifecycle = lifecycle
        self._journal = journal
        self._launch_attempt_factory = launch_attempt_factory
        self._now = now
        self._health_timeout_sec = health_timeout_sec

    def execute(self, request: UpdateRequestArtifact) -> UpdateResultArtifact:
        receipt: CommitReceipt | None = None
        phase = TransactionPhase.VERIFY
        try:
            self._record(request, phase)
            self._backend.verify(request)
            phase = TransactionPhase.PREPARE
            self._record(request, phase)
            candidate = self._backend.prepare(request)
            phase = TransactionPhase.SHUTDOWN
            self._record(request, phase)
            self._lifecycle.request_shutdown(request.transaction_id)
            phase = TransactionPhase.COMMIT
            self._record(request, phase)
            receipt = self._backend.commit(candidate)
            phase = TransactionPhase.LAUNCH
            self._record(request, phase)
            launch = self._lifecycle.launch(
                version_root=receipt.candidate_root,
                transaction_id=request.transaction_id,
                launch_attempt_id=self._launch_attempt_factory(),
                expected_version=request.target_version,
            )
            phase = TransactionPhase.HEALTH
            self._record(request, phase)
            health = self._lifecycle.await_health(launch, timeout_sec=self._health_timeout_sec)
            validate_health_relation(launch, health)
            phase = TransactionPhase.FINALIZE
            self._record(request, phase)
            self._backend.finalize(receipt)
            return UpdateResultArtifact(request.transaction_id, self._now(), "updated", request.target_version)
        except Exception as exc:
            failure = _failure_code(phase, exc)
            if receipt is None:
                return UpdateResultArtifact(request.transaction_id, self._now(), "failed", request.installed_version, failure)
            return self._rollback(request, receipt, failure)

    def _rollback(self, request: UpdateRequestArtifact, receipt: CommitReceipt, failure: FailureCode) -> UpdateResultArtifact:
        try:
            self._record(request, TransactionPhase.ROLLBACK, failure)
            self._backend.rollback(receipt)
            launch = self._lifecycle.launch(
                version_root=receipt.previous_root,
                transaction_id=request.transaction_id,
                launch_attempt_id=self._launch_attempt_factory(),
                expected_version=request.installed_version,
            )
            health = self._lifecycle.await_health(launch, timeout_sec=self._health_timeout_sec)
            validate_health_relation(launch, health)
            return UpdateResultArtifact(request.transaction_id, self._now(), "rolled_back", request.installed_version, failure)
        except Exception:
            return UpdateResultArtifact(request.transaction_id, self._now(), "failed", request.installed_version, failure, FailureCode.ROLLBACK_FAILED)

    def _record(self, request: UpdateRequestArtifact, phase: TransactionPhase, failure: FailureCode | None = None) -> None:
        self._journal.record(TransactionSnapshot(request.transaction_id, phase, request.installed_version, request.target_version, failure))


def _failure_code(phase: TransactionPhase, error: Exception) -> FailureCode:
    if isinstance(error, ManagedUpdateFailure):
        return error.code
    if phase == TransactionPhase.HEALTH and isinstance(error, TimeoutError):
        return FailureCode.HEALTH_TIMEOUT
    return {
        TransactionPhase.VERIFY: FailureCode.BUNDLE_INVALID,
        TransactionPhase.PREPARE: FailureCode.PREPARE_FAILED,
        TransactionPhase.SHUTDOWN: FailureCode.SHUTDOWN_FAILED,
        TransactionPhase.COMMIT: FailureCode.COMMIT_FAILED,
        TransactionPhase.LAUNCH: FailureCode.LAUNCH_FAILED,
        TransactionPhase.HEALTH: FailureCode.HEALTH_FAILED,
        TransactionPhase.FINALIZE: FailureCode.INTERNAL_ERROR,
    }.get(phase, FailureCode.INTERNAL_ERROR)
