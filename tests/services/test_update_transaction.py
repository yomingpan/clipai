from datetime import datetime, timezone
from pathlib import Path

import pytest

from ClipAI.core.managed_update import CommitReceipt, FailureCode, ManagedUpdateFailure, TransactionPhase, launch_attempt_id, transaction_id
from ClipAI.core.update_artifacts import LaunchReceiptArtifact, StartupHealthArtifact, UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.services.update_transaction import ManagedUpdateTransaction


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc).isoformat()


class Backend:
    def __init__(self, root: Path, events: list[str], fail: str | None = None) -> None:
        self.root, self.events, self.fail = root, events, fail

    def _step(self, name: str) -> None:
        self.events.append(name)
        if self.fail == name:
            raise RuntimeError(name)

    def verify(self, request): self._step("verify")
    def prepare(self, request):
        self._step("prepare")
        candidate = self.root / "new"
        return CandidateEnvironment(candidate, candidate / "python.exe", candidate / "main.py", request.target_version)
    def known_good_root(self, request):
        self._step("known_good_root")
        return self.root / "old"
    def commit(self, candidate):
        self._step("commit")
        return CommitReceipt(self.root / "old", candidate.root)
    def rollback(self, receipt): self._step("rollback")
    def finalize(self, receipt): self._step("finalize")


class Lifecycle:
    def __init__(self, events: list[str], fail: str | None = None) -> None:
        self.events, self.fail = events, fail

    def request_shutdown(self, transaction_id): self._step("shutdown")
    def launch(self, *, version_root, transaction_id, launch_attempt_id, expected_version):
        name = "rollback_launch" if version_root.name == "old" else "launch"
        self._step(name)
        return LaunchReceiptArtifact(transaction_id, NOW, launch_attempt_id, expected_version, (version_root / "python.exe").resolve(), 42)
    def await_health(self, launch, *, timeout_sec):
        name = "rollback_health" if launch.expected_version == "3.7.3" else "health"
        self._step(name)
        return StartupHealthArtifact(launch.transaction_id, NOW, launch.launch_attempt_id, launch.expected_version, launch.expected_version, launch.executable_path, True)
    def _step(self, name):
        self.events.append(name)
        if self.fail == name:
            if name == "health":
                raise TimeoutError(name)
            raise RuntimeError(name)


class Journal:
    def __init__(self, events: list[str]) -> None:
        self.events, self.snapshots = events, []
    def record(self, snapshot):
        self.events.append(f"journal:{snapshot.phase}")
        self.snapshots.append(snapshot)


def _request(tmp_path: Path):
    return UpdateRequestArtifact(transaction_id("tx"), NOW, "3.7.3", "3.8.0", (tmp_path / "old" / "python.exe").resolve(), 1234, (tmp_path / "b.zip").resolve(), 42, "a" * 64, "b" * 64, "release-key", (tmp_path / "install").resolve(), (tmp_path / "shared").resolve(), "managed")


def _transaction(tmp_path: Path, backend_fail=None, lifecycle_fail=None):
    events: list[str] = []
    journal = Journal(events)
    attempts = iter((launch_attempt_id("new-attempt"), launch_attempt_id("old-attempt")))
    transaction = ManagedUpdateTransaction(backend=Backend(tmp_path, events, backend_fail), lifecycle=Lifecycle(events, lifecycle_fail), journal=journal, launch_attempt_factory=lambda: next(attempts), now=lambda: NOW)
    return transaction, events, journal


def test_happy_path_journals_before_every_side_effect_and_finalizes_after_health(tmp_path: Path):
    transaction, events, journal = _transaction(tmp_path)
    result = transaction.execute(_request(tmp_path))
    assert result.outcome == "updated"
    assert [snapshot.phase for snapshot in journal.snapshots] == list(TransactionPhase)[:6] + [TransactionPhase.FINALIZE]
    assert events == ["journal:verify", "verify", "journal:prepare", "prepare", "known_good_root", "journal:shutdown", "shutdown", "journal:commit", "commit", "journal:launch", "launch", "journal:health", "health", "journal:finalize", "finalize"]


@pytest.mark.parametrize("failure,code", [("verify", FailureCode.BUNDLE_INVALID), ("prepare", FailureCode.PREPARE_FAILED), ("shutdown", FailureCode.SHUTDOWN_FAILED)])
def test_precommit_failure_leaves_old_version_active_without_rollback(tmp_path: Path, failure: str, code: FailureCode):
    transaction, events, _journal = _transaction(tmp_path, backend_fail=failure if failure != "shutdown" else None, lifecycle_fail=failure if failure == "shutdown" else None)
    result = transaction.execute(_request(tmp_path))
    assert result.outcome == "failed" and result.active_version == "3.7.3" and result.failure_code == code
    assert "rollback" not in events


def test_commit_failure_relaunches_known_good_version_after_completed_shutdown(tmp_path: Path):
    transaction, events, _journal = _transaction(tmp_path, backend_fail="commit")
    result = transaction.execute(_request(tmp_path))
    assert result.outcome == "rolled_back"
    assert result.failure_code is FailureCode.COMMIT_FAILED
    assert "rollback" not in events
    assert events.index("journal:rollback") < events.index("rollback_launch") < events.index("rollback_health")


@pytest.mark.parametrize("failure,code", [("launch", FailureCode.LAUNCH_FAILED), ("health", FailureCode.HEALTH_TIMEOUT), ("finalize", FailureCode.INTERNAL_ERROR)])
def test_postcommit_failure_restores_and_health_checks_old_version(tmp_path: Path, failure: str, code: FailureCode):
    transaction, events, _journal = _transaction(tmp_path, backend_fail=failure if failure == "finalize" else None, lifecycle_fail=failure if failure != "finalize" else None)
    result = transaction.execute(_request(tmp_path))
    assert result.outcome == "rolled_back" and result.failure_code == code
    assert events.index("journal:rollback") < events.index("rollback") < events.index("rollback_launch") < events.index("rollback_health")


def test_rollback_failure_is_explicit_and_never_claims_update_success(tmp_path: Path):
    transaction, _events, _journal = _transaction(tmp_path, backend_fail="rollback", lifecycle_fail="health")
    result = transaction.execute(_request(tmp_path))
    assert result.outcome == "failed"
    assert result.failure_code == FailureCode.HEALTH_TIMEOUT
    assert result.rollback_failure_code == FailureCode.ROLLBACK_FAILED


def test_typed_backend_failure_code_is_preserved(tmp_path: Path):
    class SignatureBackend(Backend):
        def verify(self, request):
            raise ManagedUpdateFailure(FailureCode.SIGNATURE_INVALID, "bad signature")

    events: list[str] = []
    transaction = ManagedUpdateTransaction(
        backend=SignatureBackend(tmp_path, events),
        lifecycle=Lifecycle(events),
        journal=Journal(events),
        launch_attempt_factory=lambda: launch_attempt_id("attempt"),
        now=lambda: NOW,
    )
    result = transaction.execute(_request(tmp_path))
    assert result.failure_code == FailureCode.SIGNATURE_INVALID
