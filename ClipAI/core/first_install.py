from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from ClipAI.core.managed_update_commands import InstallManagedCommand


class InstallPhase(str, Enum):
    CHECKING = "checking"
    PREPARING = "preparing"
    COMMITTING = "committing"
    INTEGRATING = "integrating"
    INSTALLED = "installed"
    INTEGRATION_INCOMPLETE = "installed_integration_incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CLEANUP_FAILED = "cleanup_failed"


@dataclass(frozen=True)
class FirstInstallSnapshot:
    transaction_id: str
    phase: InstallPhase
    error_code: str | None = None


class InstallCancellation(Protocol):
    def is_cancelled(self) -> bool: ...


class InstallAdmission(Protocol):
    def require_active(self, install_root: Path) -> None: ...
    def close(self) -> None: ...


class FirstInstallOperation(Protocol):
    def prepare(self) -> None: ...
    def commit(self) -> None: ...
    def is_committed(self) -> bool: ...
    def integrate(self) -> None: ...
    def cleanup(self) -> None: ...
    def close(self) -> None: ...


class FirstInstallBackend(Protocol):
    def begin(self, command: InstallManagedCommand, cancellation: InstallCancellation) -> FirstInstallOperation: ...


class InstallCancelled(RuntimeError):
    pass


class InstallationBusyError(RuntimeError):
    """An owned application process prevents safe removal; close it and retry."""


class UninstallPhase(str, Enum):
    REMOVING = "removing"
    REMOVED = "uninstalled"
    FAILED = "failed"


@dataclass(frozen=True)
class UninstallIntent:
    transaction_id: str
    install_root: Path
    shared_root: Path
    delete_user_data: bool = False


@dataclass(frozen=True)
class UninstallSnapshot:
    transaction_id: str
    phase: UninstallPhase
    error_code: str | None = None


class UninstallBackend(Protocol):
    def remove(self, intent: UninstallIntent) -> None: ...
