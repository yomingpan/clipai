from pathlib import Path

from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.core.update_artifacts import LaunchReceiptArtifact, StartupHealthArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.services.managed_current_launch import ManagedCurrentLaunchCoordinator


NOW = "2026-09-13T00:00:00+00:00"


class _Layout:
    def __init__(self, candidate):
        self.candidate = candidate
        self.proofs = 0

    def prove_current_install(self):
        self.proofs += 1
        return self.candidate


class _Lifecycle:
    def __init__(self, expected):
        self.expected = expected
        self.launches = []
        self.health = []

    def launch(self, **identity):
        self.launches.append(identity)
        return LaunchReceiptArtifact(
            identity["transaction_id"], NOW, identity["launch_attempt_id"],
            identity["expected_version"], self.expected.python, 123,
        )

    def await_health(self, launch, *, timeout_sec):
        self.health.append((launch, timeout_sec))
        return StartupHealthArtifact(
            launch.transaction_id, NOW, launch.launch_attempt_id,
            launch.expected_version, launch.expected_version,
            launch.executable_path, True,
        )


def test_stable_launcher_resolves_current_and_requires_matching_health(tmp_path: Path):
    root = (tmp_path / "install" / "versions" / "2.0").resolve()
    candidate = CandidateEnvironment(
        root, root / ".venv" / "Scripts" / "python.exe", root / "payload" / "main.py", "2.0",
    )
    layout = _Layout(candidate)
    lifecycle = _Lifecycle(candidate)
    coordinator = ManagedCurrentLaunchCoordinator(
        install=layout,
        lifecycle=lifecycle,
        transaction_id_factory=lambda: transaction_id("startup-1"),
        launch_attempt_factory=lambda: launch_attempt_id("attempt-1"),
        health_timeout_sec=20.0,
    )

    health = coordinator.execute()

    assert layout.proofs == 1
    assert lifecycle.launches == [{
        "version_root": candidate.root,
        "transaction_id": transaction_id("startup-1"),
        "launch_attempt_id": launch_attempt_id("attempt-1"),
        "expected_version": "2.0",
    }]
    assert lifecycle.health == [(lifecycle.health[0][0], 20.0)]
    assert health.healthy is True
