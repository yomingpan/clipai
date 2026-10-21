from __future__ import annotations

from types import SimpleNamespace

import pytest

from ClipAI.core.first_install import InstallCancelled, InstallPhase
from ClipAI.services.first_install import FirstInstallCoordinator
from ClipAI.services.first_install import UninstallCoordinator
from ClipAI.core.first_install import UninstallIntent, UninstallPhase


class Cancellation:
    cancelled = False
    def is_cancelled(self):
        return self.cancelled


class Operation:
    def __init__(self, cancellation, failure=None):
        self.cancellation, self.failure = cancellation, failure
        self.events, self.committed = [], False
    def prepare(self):
        self.events.append("prepare")
        if self.failure == "prepare":
            raise RuntimeError()
        if self.failure == "cancel":
            self.cancellation.cancelled = True
    def commit(self):
        self.events.append("commit")
        self.committed = True
        if self.failure == "partial_commit":
            raise RuntimeError()
        if self.failure == "late_cancel":
            self.cancellation.cancelled = True
    def is_committed(self):
        if self.failure == "unknown_commit":
            raise ValueError()
        return self.committed
    def integrate(self):
        self.events.append("integrate")
        if self.failure == "integrate":
            raise RuntimeError()
    def cleanup(self):
        self.events.append("cleanup")
        if self.failure == "cleanup":
            raise OSError()
    def close(self):
        self.events.append("close")


class Backend:
    def __init__(self, operation):
        self.operation = operation
        self.begun = False
    def begin(self, command, cancellation):
        self.begun = True
        return self.operation


@pytest.mark.parametrize("failure,phase,cleanup", [
    (None, InstallPhase.INSTALLED, False),
    ("prepare", InstallPhase.FAILED, True),
    ("cancel", InstallPhase.CANCELLED, True),
    ("partial_commit", InstallPhase.INTEGRATION_INCOMPLETE, False),
    ("integrate", InstallPhase.INTEGRATION_INCOMPLETE, False),
    ("late_cancel", InstallPhase.INSTALLED, False),
])
def test_first_install_settles_from_actual_commit_evidence(failure, phase, cleanup):
    cancellation = Cancellation()
    operation = Operation(cancellation, failure)
    observed = []
    result = FirstInstallCoordinator(Backend(operation)).execute(
        SimpleNamespace(transaction_id="operation-1"), cancellation=cancellation, publish=observed.append)
    assert result.phase == phase
    assert ("cleanup" in operation.events) == cleanup
    assert operation.events[-1] == "close"
    assert all(snapshot.transaction_id == "operation-1" for snapshot in observed)
    assert observed[0].phase == InstallPhase.CHECKING
    if phase == InstallPhase.INSTALLED:
        assert operation.events == ["prepare", "commit", "integrate", "close"]


def test_cancel_before_admission_never_opens_backend():
    cancellation = Cancellation()
    cancellation.cancelled = True
    backend = Backend(Operation(cancellation))
    result = FirstInstallCoordinator(backend).execute(SimpleNamespace(transaction_id="operation-1"),
                                                     cancellation=cancellation, publish=lambda _snapshot: None)
    assert result.phase == InstallPhase.CANCELLED
    assert not backend.begun


def test_unknown_commit_evidence_never_authorizes_cleanup():
    operation = Operation(Cancellation(), "unknown_commit")
    def fail_prepare():
        raise RuntimeError()
    operation.prepare = fail_prepare
    result = FirstInstallCoordinator(Backend(operation)).execute(SimpleNamespace(transaction_id="operation-1"),
        cancellation=operation.cancellation, publish=lambda _snapshot: None)
    assert result.phase == InstallPhase.CLEANUP_FAILED
    assert operation.events == ["close"]


def test_cleanup_failure_is_visible_and_releases_admission():
    operation = Operation(Cancellation(), "cleanup")
    def fail_prepare():
        raise InstallCancelled()
    operation.prepare = fail_prepare
    result = FirstInstallCoordinator(Backend(operation)).execute(SimpleNamespace(transaction_id="operation-1"),
        cancellation=operation.cancellation, publish=lambda _snapshot: None)
    assert result.phase == InstallPhase.CLEANUP_FAILED
    assert operation.events == ["cleanup", "close"]


@pytest.mark.parametrize("failure", [False, True])
def test_uninstall_success_follows_backend_settlement_and_failure_is_visible(tmp_path, failure):
    events = []
    class RemovalBackend:
        def remove(self, intent):
            events.append("remove")
            if failure:
                raise OSError()
    intent = UninstallIntent("remove-1", tmp_path / "install", tmp_path / "retained")
    snapshots = []
    result = UninstallCoordinator(RemovalBackend()).execute(intent, publish=snapshots.append)
    assert events == ["remove"]
    assert snapshots[0].phase == UninstallPhase.REMOVING
    assert result.phase == (UninstallPhase.FAILED if failure else UninstallPhase.REMOVED)
    assert all(snapshot.transaction_id == "remove-1" for snapshot in snapshots)


def test_busy_uninstall_exposes_a_safe_actionable_code(tmp_path):
    from ClipAI.core.first_install import InstallationBusyError

    class BusyBackend:
        def remove(self, intent):
            raise InstallationBusyError()

    intent = UninstallIntent("busy-remove", tmp_path / "install", tmp_path / "data")
    result = UninstallCoordinator(BusyBackend()).execute(intent, publish=lambda _: None)
    assert result.phase == UninstallPhase.FAILED
    assert result.error_code == "InstallationBusyError"
