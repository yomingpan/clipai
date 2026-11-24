from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ClipAI.core.managed_update_commands import LaunchManagedCommand
from ClipAI.platform.managed_update_lifecycle import StartupHealthReporter


RunApplication = Callable[[Callable[[], None]], None]


class ManagedLaunchExecutor:
    """Publish launch health at the runtime's proven readiness boundary."""

    def __init__(
        self,
        *,
        actual_version: str,
        executable_path: str | Path,
        now: Callable[[], str],
        run_application: RunApplication,
    ) -> None:
        self._actual_version = actual_version
        self._executable_path = Path(executable_path)
        self._now = now
        self._run_application = run_application

    def execute(self, command: LaunchManagedCommand) -> int:
        reporter = StartupHealthReporter(shared_root=command.shared_root, now=self._now)
        if self._actual_version != command.expected_version:
            reporter.report(
                transaction_id=command.transaction_id,
                launch_attempt_id=command.launch_attempt_id,
                expected_version=command.expected_version,
                actual_version=self._actual_version,
                executable_path=self._executable_path,
                healthy=False,
            )
            return 1

        reported = False

        def report_started() -> None:
            nonlocal reported
            if reported:
                raise RuntimeError("managed runtime readiness was reported more than once")
            reporter.report(
                transaction_id=command.transaction_id,
                launch_attempt_id=command.launch_attempt_id,
                expected_version=command.expected_version,
                actual_version=self._actual_version,
                executable_path=self._executable_path,
                healthy=True,
            )
            reported = True

        self._run_application(report_started)
        if not reported:
            raise RuntimeError("managed runtime exited without reporting readiness")
        return 0
