from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import TransactionId
from ClipAI.core.update_artifacts import HandoffReadyArtifact
from ClipAI.core.update_ports import ManagedUpdateHandoff
from ClipAI.core.update_preparation import ManagedUpdatePreparation
from ClipAI.services.managed_update_coordinator import ManagedUpdateCoordinator


class ManagedUpdateHandoffExecutor:
    """Cross the app lifecycle boundary only after the host is ready."""

    def __init__(
        self,
        *,
        coordinator: ManagedUpdateCoordinator,
        handoff: ManagedUpdateHandoff,
        request_shutdown: Callable[[], None],
    ) -> None:
        self._coordinator = coordinator
        self._handoff = handoff
        self._request_shutdown = request_shutdown

    def execute(
        self,
        identity: ManagedUpdateClientIdentity,
        transaction_id: TransactionId,
        *,
        preparation: ManagedUpdatePreparation | None = None,
    ) -> HandoffReadyArtifact | None:
        preparation = preparation or ManagedUpdatePreparation()
        preparation.check_cancelled()
        request = self._coordinator.prepare(identity, transaction_id, preparation=preparation)
        preparation.check_cancelled()
        if request is None:
            return None
        preparation.report_phase("preparing")
        preparation.check_cancelled()
        readiness = self._handoff.prepare(request)
        self._request_shutdown()
        return readiness
