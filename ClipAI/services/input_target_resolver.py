from __future__ import annotations

from ClipAI.core.models import ActiveWorkflowContext, ExternalFallback, InputDocument, InputTarget


class InputTargetResolver:
    def resolve(
        self,
        context: ActiveWorkflowContext | None,
        external_fallback: ExternalFallback = "selection_or_clipboard",
    ) -> InputTarget:
        # An open popup is the authoritative input surface. Its selection (or
        # full displayed result) must win before we attempt any OS selection or
        # clipboard capture, regardless of the action's external fallback policy.
        del external_fallback  # The executor applies this only after popup context is exhausted.
        if context is None:
            return InputTarget("external_text")
        text = context.selected_text.strip() if context.selected_text and context.selected_text.strip() else context.content.strip()
        if not text:
            return InputTarget("external_text")
        return InputTarget(
            "workflow_result",
            InputDocument(text, "workflow_result", context.workflow_id, context.step_id),
        )
