from __future__ import annotations

from ClipAI.core.errors import CancelledError
from ClipAI.core.models import ForegroundTarget
from ClipAI.core.ports import ForegroundTargetReader, OperationTracker
from ClipAI.core.state import CancellationToken
from ClipAI.services.output_actions import OutputActions


class WriteResultSink:
    def __init__(self, targets: ForegroundTargetReader, outputs: OutputActions, tracker: OperationTracker | None = None) -> None:
        self._targets = targets
        self._outputs = outputs
        self._tracker = tracker

    def write_result(self, text: str, target: ForegroundTarget | None, workflow_id: str, cancellation: CancellationToken) -> None:
        if cancellation.is_cancelled:
            raise CancelledError("Write was cancelled.")
        if target is None or self._targets.current() != target:
            raise CancelledError("Write was not applied because the target window changed.")
        if not self._outputs.can_paste:
            raise CancelledError("Write is not available on this device.")
        operation = self._tracker.start(f"paste:{workflow_id}", "paste") if self._tracker else None
        try:
            self._outputs.paste(text)
        except BaseException:
            if operation is not None:
                operation.fail()
            raise
        if operation is not None:
            operation.succeed()
