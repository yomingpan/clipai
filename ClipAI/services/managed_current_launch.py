from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_update import LaunchAttemptId, TransactionId
from ClipAI.core.update_artifacts import StartupHealthArtifact
from ClipAI.core.update_ports import ManagedApplicationLifecycle, ManagedInstallReader


class ManagedCurrentLaunchCoordinator:
    """Resolve and health-check one normal launch from the atomic pointer."""

    def __init__(
        self,
        *,
        install: ManagedInstallReader,
        lifecycle: ManagedApplicationLifecycle,
        transaction_id_factory: Callable[[], TransactionId],
        launch_attempt_factory: Callable[[], LaunchAttemptId],
        health_timeout_sec: float = 20.0,
    ) -> None:
        if health_timeout_sec <= 0:
            raise ValueError("managed launch health budget must be positive")
        self._install = install
        self._lifecycle = lifecycle
        self._transaction_id_factory = transaction_id_factory
        self._launch_attempt_factory = launch_attempt_factory
        self._health_timeout_sec = health_timeout_sec

    def execute(self) -> StartupHealthArtifact:
        current = self._install.prove_current_install()
        launch = self._lifecycle.launch(
            version_root=current.root,
            transaction_id=self._transaction_id_factory(),
            launch_attempt_id=self._launch_attempt_factory(),
            expected_version=current.version,
        )
        return self._lifecycle.await_health(launch, timeout_sec=self._health_timeout_sec)
