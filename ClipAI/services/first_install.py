from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.first_install import (
    FirstInstallBackend, FirstInstallOperation, FirstInstallSnapshot,
    InstallCancellation, InstallCancelled, InstallPhase,
    RetainedDataUninstallBackend, RetainedDataUninstallIntent, UninstallPhase, UninstallSnapshot,
)
from ClipAI.core.managed_update_commands import InstallManagedCommand


class FirstInstallCoordinator:
    """One first-install policy owner; native adapters supply operation evidence."""

    def __init__(self, backend: FirstInstallBackend) -> None:
        self._backend = backend

    def execute(self, command: InstallManagedCommand, *, cancellation: InstallCancellation,
                publish: Callable[[FirstInstallSnapshot], None]) -> FirstInstallSnapshot:
        operation: FirstInstallOperation | None = None

        def emit(phase: InstallPhase, error: str | None = None) -> FirstInstallSnapshot:
            snapshot = FirstInstallSnapshot(str(command.transaction_id), phase, error)
            publish(snapshot)
            return snapshot

        try:
            emit(InstallPhase.CHECKING)
            if cancellation.is_cancelled():
                raise InstallCancelled()
            operation = self._backend.begin(command, cancellation)
            emit(InstallPhase.PREPARING)
            operation.prepare()
            if cancellation.is_cancelled():
                raise InstallCancelled()
            # Commit and native integration settle before cancellation is observed
            # again. A late cancel never removes a committed installation.
            emit(InstallPhase.COMMITTING)
            operation.commit()
            emit(InstallPhase.INTEGRATING)
            operation.integrate()
            return emit(InstallPhase.INSTALLED)
        except Exception as exc:
            code = type(exc).__name__
            if operation is not None:
                try:
                    if operation.is_committed():
                        return emit(InstallPhase.INTEGRATION_INCOMPLETE, code)
                except Exception as evidence_error:
                    return emit(InstallPhase.CLEANUP_FAILED, type(evidence_error).__name__)
            if operation is not None:
                try:
                    operation.cleanup()
                except Exception as cleanup_error:
                    return emit(InstallPhase.CLEANUP_FAILED, type(cleanup_error).__name__)
            phase = InstallPhase.CANCELLED if isinstance(exc, InstallCancelled) else InstallPhase.FAILED
            return emit(phase, code)
        finally:
            if operation is not None:
                operation.close()


class RetainedDataUninstallCoordinator:
    """An explicit retained-data intent; success follows actual native settlement."""

    def __init__(self, backend: RetainedDataUninstallBackend) -> None:
        self._backend = backend

    def execute(self, intent: RetainedDataUninstallIntent, *, publish: Callable[[UninstallSnapshot], None]) -> UninstallSnapshot:
        publish(UninstallSnapshot(intent.transaction_id, UninstallPhase.REMOVING))
        try:
            self._backend.remove(intent)
        except Exception as exc:
            result = UninstallSnapshot(intent.transaction_id, UninstallPhase.FAILED, type(exc).__name__)
        else:
            result = UninstallSnapshot(intent.transaction_id, UninstallPhase.REMOVED)
        publish(result)
        return result
