from __future__ import annotations

from collections.abc import Callable

from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import TransactionId
from ClipAI.core.update_artifacts import HandoffReadyArtifact
from ClipAI.core.update_ports import ManagedUpdateHandoff
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
    ) -> HandoffReadyArtifact | None:
        request = self._coordinator.prepare(identity, transaction_id)
        if request is None:
            return None
        readiness = self._handoff.prepare(request)
        self._request_shutdown()
        return readiness
