from __future__ import annotations

from ClipAI.core.models import ActiveWorkflowContext, InputDocument, InputPolicy, InputTarget


class InputTargetResolver:
    def resolve(
        self,
        policy: InputPolicy,
        context: ActiveWorkflowContext | None,
    ) -> InputTarget:
        if policy != "contextual_text" or context is None:
            return InputTarget("external_text")
        text = context.selected_text.strip() if context.selected_text and context.selected_text.strip() else context.content.strip()
        if not text:
            return InputTarget("external_text")
        return InputTarget(
            "workflow_result",
            InputDocument(text, "workflow_result", context.workflow_id, context.step_id),
        )
