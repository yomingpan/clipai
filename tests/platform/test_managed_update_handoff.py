from pathlib import Path

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_artifacts import HandoffReadyArtifact, UpdateRequestArtifact, UpdateResultArtifact
from ClipAI.platform.managed_update_handoff import SubprocessManagedUpdateHandoff
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore


NOW = "2026-09-13T00:00:00+00:00"


class _Process:
    pid = 987

    def __init__(self, exit_code=None) -> None:
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


def _request(tmp_path: Path) -> UpdateRequestArtifact:
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    return UpdateRequestArtifact(
        transaction_id("tx-1"), NOW, "1.0", "2.0",
        (install_root / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe").resolve(),
        321, (shared_root / "bundle.zip").resolve(), 42, "a" * 64, "b" * 64,
        "release-key", install_root, shared_root, "managed-1",
    )


def _runtime_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    launcher_python = (tmp_path / "launcher" / "python.exe").resolve()
    launcher_entrypoint = (tmp_path / "launcher" / "clipai-managed.py").resolve()
    base_python = (tmp_path / "base" / "python.exe").resolve()
    for path in (launcher_python, launcher_entrypoint, base_python):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    return launcher_python, launcher_entrypoint, base_python


def test_handoff_publishes_request_starts_isolated_host_and_accepts_exact_readiness(tmp_path: Path):
    request = _request(tmp_path)
    launcher_python, launcher_entrypoint, base_python = _runtime_paths(tmp_path)
    calls = []
    tick = [0.0]

    def start(arguments, environment, cwd):
        calls.append((list(arguments), dict(environment), cwd))
        return _Process()

    def sleep(seconds):
        ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1").write(
            HandoffReadyArtifact(
                request.transaction_id, NOW,
                request.install_root / "versions" / "2.0",
                request.install_root / "versions" / "2.0" / ".venv" / "Scripts" / "python.exe",
                request.manifest_sha256, request.target_version,
            )
        )
        tick[0] += seconds

    handoff = SubprocessManagedUpdateHandoff(
        launcher_python=launcher_python,
        launcher_entrypoint=launcher_entrypoint,
        base_python=base_python,
        environment={"PATH": "stable", "PYTHONPATH": "parent", "VIRTUAL_ENV": "parent"},
        start_process=start,
        monotonic=lambda: tick[0],
        sleep=sleep,
    )

    ready = handoff.prepare(request)

    assert ready.expected_version == "2.0"
    stored = ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1").read("request")
    assert stored == request
    arguments, environment, cwd = calls[0]
    assert arguments == [
        str(launcher_python), "-I", str(launcher_entrypoint), "host",
        "--shared-root", str(request.shared_root), "--transaction-id", "tx-1",
        "--install-root", str(request.install_root), "--base-python", str(base_python),
    ]
    assert cwd == launcher_entrypoint.parent
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert "PYTHONPATH" not in environment and "VIRTUAL_ENV" not in environment


def test_handoff_propagates_terminal_host_failure(tmp_path: Path):
    request = _request(tmp_path)
    launcher_python, launcher_entrypoint, base_python = _runtime_paths(tmp_path)
    store = ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1")
    tick = [0.0]

    def sleep(seconds):
        store.write(UpdateResultArtifact(
            request.transaction_id, NOW, "failed", request.installed_version, FailureCode.IDENTITY_INELIGIBLE,
        ))
        tick[0] += seconds

    handoff = SubprocessManagedUpdateHandoff(
        launcher_python=launcher_python, launcher_entrypoint=launcher_entrypoint,
        base_python=base_python, environment={}, start_process=lambda *_args: _Process(),
        monotonic=lambda: tick[0], sleep=sleep,
    )

    with pytest.raises(ManagedUpdateFailure) as raised:
        handoff.prepare(request)
    assert raised.value.code is FailureCode.IDENTITY_INELIGIBLE


@pytest.mark.parametrize(("exit_code", "expected_code"), [
    (1, FailureCode.HANDOFF_FAILED),
    (None, FailureCode.HANDOFF_TIMEOUT),
])
def test_handoff_fails_when_host_exits_or_readiness_times_out(tmp_path: Path, exit_code, expected_code):
    request = _request(tmp_path)
    launcher_python, launcher_entrypoint, base_python = _runtime_paths(tmp_path)
    tick = [0.0]
    handoff = SubprocessManagedUpdateHandoff(
        launcher_python=launcher_python, launcher_entrypoint=launcher_entrypoint,
        base_python=base_python, environment={}, start_process=lambda *_args: _Process(exit_code),
        monotonic=lambda: tick[0], sleep=lambda seconds: tick.__setitem__(0, tick[0] + seconds),
        timeout_sec=0.1,
    )

    with pytest.raises(ManagedUpdateFailure) as raised:
        handoff.prepare(request)
    assert raised.value.code is expected_code
