from pathlib import Path

import pytest

from ClipAI.app.managed_update_handoff import ManagedUpdateHandoffExecutor
from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_artifacts import HandoffReadyArtifact, UpdateRequestArtifact


NOW = "2026-09-13T00:00:00+00:00"


class _Coordinator:
    def __init__(self, request):
        self.request = request

    def prepare(self, identity, transaction):
        return self.request


class _Handoff:
    def __init__(self, ready=None, error=None, events=None):
        self.ready = ready
        self.error = error
        self.events = events if events is not None else []

    def prepare(self, request):
        self.events.append("handoff:ready")
        if self.error is not None:
            raise self.error
        return self.ready


def _identity(tmp_path: Path) -> ManagedUpdateClientIdentity:
    return ManagedUpdateClientIdentity(
        "1.0", "1.0", (tmp_path / "old-python.exe").resolve(), 321,
        (tmp_path / "install").resolve(), (tmp_path / "shared").resolve(), "managed-1",
    )


def _request(tmp_path: Path) -> UpdateRequestArtifact:
    identity = _identity(tmp_path)
    return UpdateRequestArtifact(
        transaction_id("tx-1"), NOW, "1.0", "2.0", identity.installed_executable,
        identity.installed_process_id, (tmp_path / "bundle.zip").resolve(), 42,
        "a" * 64, "b" * 64, "release-key", identity.install_root,
        identity.shared_root, identity.managed_install_id,
    )


def test_app_requests_normal_shutdown_only_after_matching_handoff_readiness(tmp_path: Path):
    request = _request(tmp_path)
    ready = HandoffReadyArtifact(
        request.transaction_id, NOW, request.install_root / "versions" / "2.0",
        request.install_root / "versions" / "2.0" / ".venv" / "Scripts" / "python.exe",
        request.manifest_sha256, request.target_version,
    )
    events = []
    executor = ManagedUpdateHandoffExecutor(
        coordinator=_Coordinator(request),
        handoff=_Handoff(ready=ready, events=events),
        request_shutdown=lambda: events.append("runtime:shutdown"),
    )

    assert executor.execute(_identity(tmp_path), transaction_id("tx-1")) == ready
    assert events == ["handoff:ready", "runtime:shutdown"]


def test_app_keeps_running_when_no_update_or_handoff_failure(tmp_path: Path):
    shutdowns = []
    no_update = ManagedUpdateHandoffExecutor(
        coordinator=_Coordinator(None), handoff=_Handoff(),
        request_shutdown=lambda: shutdowns.append("stop"),
    )
    assert no_update.execute(_identity(tmp_path), transaction_id("tx-none")) is None

    failed = ManagedUpdateHandoffExecutor(
        coordinator=_Coordinator(_request(tmp_path)),
        handoff=_Handoff(error=ManagedUpdateFailure(FailureCode.HANDOFF_FAILED, "failed")),
        request_shutdown=lambda: shutdowns.append("stop"),
    )
    with pytest.raises(ManagedUpdateFailure):
        failed.execute(_identity(tmp_path), transaction_id("tx-1"))
    assert shutdowns == []
