from ClipAI.core.models import ActiveWorkflowContext
from ClipAI.services.input_target_resolver import InputTargetResolver


def test_contextual_input_prefers_popup_selection() -> None:
    context = ActiveWorkflowContext("w", "s", "full result", " selected ")
    target = InputTargetResolver().resolve("contextual_text", context)
    assert target.document.text == "selected"
    assert target.document.source == "workflow_result"


def test_contextual_input_falls_back_to_full_result() -> None:
    context = ActiveWorkflowContext("w", "s", "full result", None)
    target = InputTargetResolver().resolve("contextual_text", context)
    assert target.document.text == "full result"


def test_external_policy_still_prefers_popup_context() -> None:
    context = ActiveWorkflowContext("w", "s", "full result", "selected")
    target = InputTargetResolver().resolve("external_text", context)
    assert target.kind == "workflow_result"
    assert target.document.text == "selected"
<<<<<<< HEAD
=======


def test_external_policy_falls_back_to_full_popup_result() -> None:
    context = ActiveWorkflowContext("w", "s", "full result", None)
    target = InputTargetResolver().resolve("external_text", context)
    assert target.document.text == "full result"
>>>>>>> ui-optimization
