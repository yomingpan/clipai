from pathlib import Path

from ClipAI.app.managed_update_launch import ManagedLaunchExecutor
from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.core.managed_update_commands import LaunchManagedCommand
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore


NOW = "2026-09-13T00:00:00+00:00"


def _command(tmp_path: Path, *, expected_version: str = "2.0") -> LaunchManagedCommand:
    return LaunchManagedCommand(
        shared_root=(tmp_path / "shared").resolve(),
        install_root=(tmp_path / "install").resolve(),
        transaction_id=transaction_id("tx-1"),
        launch_attempt_id=launch_attempt_id("attempt-1"),
        expected_version=expected_version,
    )


def test_launch_reports_matching_health_only_from_runtime_started_callback(tmp_path: Path):
    command = _command(tmp_path)
    executable = (tmp_path / "install" / "versions" / "2.0" / ".venv" / "Scripts" / "python.exe").resolve()
    observations: list[str] = []

    def run_application(on_started):
        store = ManagedUpdateArtifactStore(shared_root=command.shared_root, transaction_id="tx-1")
        assert not store.path("startup_health").exists()
        observations.append("runtime:start")
        on_started()
        assert store.read("startup_health").healthy is True
        observations.append("view:run")

    executor = ManagedLaunchExecutor(
        actual_version="2.0",
        executable_path=executable,
        now=lambda: NOW,
        run_application=run_application,
    )

    assert executor.execute(command) == 0
    health = ManagedUpdateArtifactStore(shared_root=command.shared_root, transaction_id="tx-1").read("startup_health")
    assert (health.launch_attempt_id, health.expected_version, health.actual_version) == (
        launch_attempt_id("attempt-1"),
        "2.0",
        "2.0",
    )
    assert health.executable_path == executable
    assert observations == ["runtime:start", "view:run"]


def test_launch_version_mismatch_reports_unhealthy_without_starting_runtime(tmp_path: Path):
    command = _command(tmp_path)
    starts: list[bool] = []
    executor = ManagedLaunchExecutor(
        actual_version="1.0",
        executable_path=(tmp_path / "python.exe").resolve(),
        now=lambda: NOW,
        run_application=lambda _started: starts.append(True),
    )

    assert executor.execute(command) == 1
    health = ManagedUpdateArtifactStore(shared_root=command.shared_root, transaction_id="tx-1").read("startup_health")
    assert health.healthy is False
    assert (health.expected_version, health.actual_version) == ("2.0", "1.0")
    assert starts == []
