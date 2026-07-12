from ClipAI.core.models import ActiveWorkflowContext
from ClipAI.services.input_target_resolver import InputTargetResolver


def test_popup_selection_has_first_precedence() -> None:
    context = ActiveWorkflowContext("w", "s", "full result", " selected ")
    target = InputTargetResolver().resolve(context)
    assert target.document.text == "selected"
    assert target.document.source == "workflow_result"


def test_popup_content_is_used_without_selection() -> None:
    context = ActiveWorkflowContext("w", "s", "full result", None)
    target = InputTargetResolver().resolve(context)
    assert target.document.text == "full result"


def test_missing_popup_context_falls_back_to_external_input() -> None:
    target = InputTargetResolver().resolve(None, "clipboard")
    assert target.kind == "external_text"
    assert target.document is None
