from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ClipAI.core.commands import SubmitActionFeedback
from ClipAI.core.models import ActionFeedbackRecord, WorkflowStep
from ClipAI.core.ports import ActionFeedbackStore


class ActionFeedbackService:
    def __init__(
        self,
        store: ActionFeedbackStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._clock = clock

    def record(self, workflow_id: str, step: WorkflowStep, command: SubmitActionFeedback) -> ActionFeedbackRecord:
        if command.session_id != workflow_id or command.step_id != step.step_id:
            raise ValueError("feedback target does not match the completed step")
        contract = step.feedback_contract
        if contract is None:
            raise ValueError("feedback is not enabled for this action")
        if command.outcome == "needs_adjustment":
            allowed = {reason.id for reason in contract.reasons}
            if command.reason not in allowed:
                raise ValueError("select a valid feedback reason")
        elif command.reason:
            raise ValueError("feedback reason is only valid when adjustment is needed")
        record = ActionFeedbackRecord(
            record_schema_version=1,
            feedback_id=command.operation_id,
            created_at=self._clock().astimezone(timezone.utc).isoformat(),
            workflow_id=workflow_id,
            step_id=step.step_id,
            action_id=step.action_id,
            action_version=step.action_version,
            press_type=step.press_type,
            provider=step.provider,
            model=step.model,
            input_source=step.input_source,
            outcome=command.outcome,
            reason=command.reason,
            note=command.note.strip(),
            input_text=step.input_text if command.save_case else None,
            result_text=step.result_text if command.save_case else None,
        )
        self._store.append(record)
        return record
