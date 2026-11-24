from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.state import CancellationToken


ManagedUpdatePreparationPhase: TypeAlias = Literal["downloading", "preparing"]


@dataclass(frozen=True)
class ManagedUpdatePreparation:
    """One operation's cancellation and semantic preparation-stage reports."""

    cancellation: CancellationToken = field(default_factory=CancellationToken)
    report_phase: Callable[[ManagedUpdatePreparationPhase], None] = lambda _phase: None

    def check_cancelled(self) -> None:
        if self.cancellation.is_cancelled:
            raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "update preparation cancelled")
