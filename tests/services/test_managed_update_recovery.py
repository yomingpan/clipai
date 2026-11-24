from datetime import datetime, timezone
from pathlib import Path

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, TransactionPhase, TransactionSnapshot, launch_attempt_id, transaction_id
from ClipAI.core.update_artifacts import LaunchReceiptArtifact, StartupHealthArtifact, UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.services.managed_update_recovery import ManagedUpdateRecovery


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc).isoformat()


class _Backend:
    def __init__(self, old, events, fail=False):
        self.old, self.events, self.fail = old, events, fail

    def restore_known_good(self, request):
        self.events.append("restore")
        if self.fail:
            raise ManagedUpdateFailure(FailureCode.ROLLBACK_FAILED, "restore failed")
        return self.old


class _Lifecycle:
    def __init__(self, events, old):
        self.events, self.old = events, old

    def launch(self, **identity):
        self.events.append("launch-old")
        return LaunchReceiptArtifact(
            identity["transaction_id"], NOW, identity["launch_attempt_id"],
            identity["expected_version"], self.old.python, 41,
        )

    def await_health(self, launch, *, timeout_sec):
        self.events.append("health-old")
        return StartupHealthArtifact(
            launch.transaction_id, NOW, launch.launch_attempt_id,
            launch.expected_version, launch.expected_version,
            launch.executable_path, True,
        )


class _Journal:
    def __init__(self, events):
        self.events = events

    def record(self, snapshot):
        self.events.append(("journal", snapshot.phase, snapshot.failure_code))


def _request(tmp_path: Path) -> UpdateRequestArtifact:
    return UpdateRequestArtifact(
        transaction_id("tx-1"), NOW, "1.0", "2.0",
        (tmp_path / "install" / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe").resolve(),
        123, (tmp_path / "bundle.zip").resolve(), 42, "a" * 64, "b" * 64,
        "release-key", (tmp_path / "install").resolve(), (tmp_path / "shared").resolve(), "managed-1",
    )


def test_recovery_journals_restores_and_health_checks_old_version(tmp_path: Path):
    request = _request(tmp_path)
    old = CandidateEnvironment(
        request.install_root / "versions" / "1.0", request.installed_executable,
        request.install_root / "versions" / "1.0" / "payload" / "main.py", "1.0",
    )
    events = []
    recovery = ManagedUpdateRecovery(
        backend=_Backend(old, events), lifecycle=_Lifecycle(events, old), journal=_Journal(events),
        launch_attempt_factory=lambda: launch_attempt_id("recovery-attempt"), now=lambda: NOW,
    )

    result = recovery.execute(
        request,
        TransactionSnapshot(request.transaction_id, TransactionPhase.HEALTH, "1.0", "2.0"),
    )

    assert result.outcome == "rolled_back"
    assert result.active_version == "1.0"
    assert result.failure_code is FailureCode.UPDATE_INTERRUPTED
    assert events == [
        ("journal", TransactionPhase.ROLLBACK, FailureCode.UPDATE_INTERRUPTED),
        "restore", "launch-old", "health-old",
    ]


def test_recovery_never_claims_success_when_old_version_cannot_be_restored(tmp_path: Path):
    request = _request(tmp_path)
    old = CandidateEnvironment(
        request.install_root / "versions" / "1.0", request.installed_executable,
        request.install_root / "versions" / "1.0" / "payload" / "main.py", "1.0",
    )
    events = []
    recovery = ManagedUpdateRecovery(
        backend=_Backend(old, events, fail=True), lifecycle=_Lifecycle(events, old), journal=_Journal(events),
        launch_attempt_factory=lambda: launch_attempt_id("recovery-attempt"), now=lambda: NOW,
    )

    result = recovery.execute(
        request,
        TransactionSnapshot(request.transaction_id, TransactionPhase.COMMIT, "1.0", "2.0"),
    )

    assert result.outcome == "failed"
    assert result.failure_code is FailureCode.UPDATE_INTERRUPTED
    assert result.rollback_failure_code is FailureCode.ROLLBACK_FAILED
    assert "launch-old" not in events
