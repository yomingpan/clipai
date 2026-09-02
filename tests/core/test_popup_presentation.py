from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from ClipAI.core.models import ActionFeedbackContract, FeedbackReason, WorkflowStep
from ClipAI.core.popup_presentation import PopupPresentationModel, project_popup_presentation
from ClipAI.core.state import SessionSnapshot, SessionStatus


def _contract() -> ActionFeedbackContract:
    return ActionFeedbackContract(
        "AI helps",
        "AI does not decide",
        (FeedbackReason("other", "Other"),),
    )


def _step(step_id: str = "step-1") -> WorkflowStep:
    return WorkflowStep(step_id, "action", "Action", "input", "result", "plain_text")


def test_popup_presentation_model_is_frozen_and_excludes_content_and_flash() -> None:
    model = project_popup_presentation(SessionSnapshot(
        "workflow-1",
        1,
        SessionStatus.CREATED,
        "action",
        "Action",
        "model",
    ))

    assert isinstance(model, PopupPresentationModel)
    assert "content" not in {field.name for field in fields(model)}
    assert "flash" not in {field.name for field in fields(model)}
    with pytest.raises(FrozenInstanceError):
        model.title = "changed"  # type: ignore[misc]


def test_completed_displayed_step_projects_feedback_and_unseen_guidance() -> None:
    contract = _contract()
    step = _step()
    snapshot = SessionSnapshot(
        "workflow-1",
        1,
        SessionStatus.COMPLETED,
        "action",
        "Action",
        "model",
        source_preview="Selection",
        pinned=True,
        available_actions=("speaker", "copy", "follow_up"),
        speaking=True,
        steps=(step,),
        displayed_step_index=0,
        can_navigate_back=True,
        action_feedback_contract=contract,
        input_source="selection",
        feedback_state="pending",
        feedback_message="Saving",
        show_guidance_hint=True,
    )

    model = project_popup_presentation(snapshot, guidance_already_shown=False)

    assert model.title == "Action"
    assert model.model == "model"
    assert model.source_preview == "Selection"
    assert model.pinned is True
    assert model.back is True
    assert model.contract is contract
    assert model.input_source == "selection"
    assert model.guidance is True
    assert model.enabled_actions == ("speaker", "copy", "follow_up")
    assert model.speaking is True
    assert model.feedback is not None
    assert model.feedback.step_id == "step-1"
    assert model.feedback.contract is contract
    assert model.feedback.state == "pending"
    assert model.feedback.message == "Saving"


@pytest.mark.parametrize(
    ("status", "displayed_step_index", "contract"),
    (
        (SessionStatus.REQUESTING_PROVIDER, 0, _contract()),
        (SessionStatus.COMPLETED, -1, _contract()),
        (SessionStatus.COMPLETED, 1, _contract()),
        (SessionStatus.COMPLETED, 0, None),
    ),
)
def test_feedback_requires_completed_contract_and_valid_displayed_step(
    status: SessionStatus,
    displayed_step_index: int,
    contract: ActionFeedbackContract | None,
) -> None:
    model = project_popup_presentation(SessionSnapshot(
        "workflow-1",
        1,
        status,
        "action",
        "Action",
        "model",
        steps=(_step(),),
        displayed_step_index=displayed_step_index,
        action_feedback_contract=contract,
    ))

    assert model.feedback is None


def test_guidance_requires_completed_flag_and_caller_reports_not_shown() -> None:
    completed = SessionSnapshot(
        "workflow-1",
        1,
        SessionStatus.COMPLETED,
        "action",
        "Action",
        "model",
        show_guidance_hint=True,
    )

    assert project_popup_presentation(completed).guidance is True
    assert project_popup_presentation(completed, guidance_already_shown=True).guidance is False
    assert project_popup_presentation(
        completed.evolve(status=SessionStatus.REQUESTING_PROVIDER),
    ).guidance is False


def test_contextual_question_excludes_follow_up_from_baseline_actions() -> None:
    model = project_popup_presentation(SessionSnapshot(
        "workflow-1",
        1,
        SessionStatus.CONTEXT_QUESTION,
        "contextual_question",
        "Ask this",
        "model",
        available_actions=("copy", "follow_up"),
    ))

    assert model.enabled_actions == ("copy",)
