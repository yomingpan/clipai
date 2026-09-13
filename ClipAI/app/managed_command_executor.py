from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_update_commands import (
    HostManagedCommand,
    InstallManagedCommand,
    LaunchManagedCommand,
    ManagedCommand,
    SelfcheckManagedCommand,
)


InstallHandler = Callable[[InstallManagedCommand], int]
LaunchHandler = Callable[[LaunchManagedCommand], int]
HostHandler = Callable[[HostManagedCommand], int]
SelfcheckHandler = Callable[[SelfcheckManagedCommand], int]


class ManagedCommandExecutor:
    """Route the single managed CLI seam to command-specific composition."""

    def __init__(
        self,
        *,
        install: InstallHandler,
        launch: LaunchHandler,
        host: HostHandler,
        selfcheck: SelfcheckHandler,
    ) -> None:
        self._install = install
        self._launch = launch
        self._host = host
        self._selfcheck = selfcheck

    def execute(self, command: ManagedCommand) -> int:
        if isinstance(command, InstallManagedCommand):
            return self._install(command)
        if isinstance(command, LaunchManagedCommand):
            return self._launch(command)
        if isinstance(command, HostManagedCommand):
            return self._host(command)
        return self._selfcheck(command)
