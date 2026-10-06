from dataclasses import replace
from pathlib import Path

import pytest

from ClipAI.app.managed_update_handoff import ManagedUpdateHandoffExecutor
from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_artifacts import HandoffReadyArtifact, UpdateRequestArtifact
from ClipAI.platform.managed_update_handoff import SubprocessManagedUpdateHandoff
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore


NOW = "2026-09-13T00:00:00+00:00"


class _Coordinator:
    def __init__(self, request):
        self.request = request

    def prepare(self, identity, transaction, *, preparation=None):
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


def test_app_waits_for_78_second_host_preparation_before_normal_shutdown(tmp_path: Path):
    request = _request(tmp_path)
    launcher_python = tmp_path / "launcher" / "python.exe"
    launcher_entrypoint = tmp_path / "launcher" / "clipai-managed.py"
    base_python = tmp_path / "base" / "python.exe"
    for path in (launcher_python, launcher_entrypoint, base_python):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    store = ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1")
    clock = [0.0]
    shutdown_at = []

    class PreparingHost:
        pid = 987

        def poll(self):
            return None

    def advance(seconds):
        clock[0] += seconds
        if clock[0] == 78.0:
            store.write(HandoffReadyArtifact(
                request.transaction_id, NOW, request.install_root / "versions" / "2.0",
                request.install_root / "versions" / "2.0" / ".venv" / "Scripts" / "python.exe",
                request.manifest_sha256, request.target_version,
            ))

    executor = ManagedUpdateHandoffExecutor(
        coordinator=_Coordinator(request),
        handoff=SubprocessManagedUpdateHandoff(
            launcher_python=launcher_python, launcher_entrypoint=launcher_entrypoint,
            base_python=base_python, environment={}, start_process=lambda *_: PreparingHost(),
            monotonic=lambda: clock[0], sleep=advance, poll_interval_sec=1.0,
        ),
        request_shutdown=lambda: shutdown_at.append(clock[0]),
    )
    ready = executor.execute(_identity(tmp_path), request.transaction_id)
    assert ready.expected_version == "2.0"
    assert shutdown_at == [78.0]


def test_late_readiness_from_timed_out_transaction_cannot_shutdown_retry(tmp_path: Path):
    old_request = _request(tmp_path)
    retry_request = replace(old_request, transaction_id=transaction_id("tx-2"))
    paths = [tmp_path / "launcher" / "python.exe", tmp_path / "launcher" / "clipai-managed.py",
             tmp_path / "base" / "python.exe"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    clock = [0.0]
    shutdown_at = []

    class PreparingHost:
        pid = 987

        def poll(self):
            return None

    def advance(seconds):
        clock[0] += seconds
        request = {21.0: old_request, 23.0: retry_request}.get(clock[0])
        if request is not None:
            ManagedUpdateArtifactStore(
                shared_root=request.shared_root, transaction_id=str(request.transaction_id),
            ).write(HandoffReadyArtifact(
                request.transaction_id, NOW, request.install_root / "versions" / "2.0",
                request.install_root / "versions" / "2.0" / ".venv" / "Scripts" / "python.exe",
                request.manifest_sha256, request.target_version,
            ))

    coordinator = _Coordinator(old_request)
    executor = ManagedUpdateHandoffExecutor(
        coordinator=coordinator,
        handoff=SubprocessManagedUpdateHandoff(
            launcher_python=paths[0], launcher_entrypoint=paths[1], base_python=paths[2],
            environment={}, start_process=lambda *_: PreparingHost(),
            monotonic=lambda: clock[0], sleep=advance, timeout_sec=20.0, poll_interval_sec=1.0,
        ),
        request_shutdown=lambda: shutdown_at.append(clock[0]),
    )
    with pytest.raises(ManagedUpdateFailure) as raised:
        executor.execute(_identity(tmp_path), old_request.transaction_id)
    assert raised.value.code is FailureCode.HANDOFF_TIMEOUT
    assert clock[0] == 20.0 and shutdown_at == []
    coordinator.request = retry_request
    ready = executor.execute(_identity(tmp_path), retry_request.transaction_id)
    assert ready.transaction_id == retry_request.transaction_id
    assert shutdown_at == [23.0]
