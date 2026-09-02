from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.models import ActionFeedbackContract, FeedbackOperationState
from ClipAI.core.state import SessionSnapshot, SessionStatus


@dataclass(frozen=True)
class PopupFeedbackModel:
    step_id: str
    contract: ActionFeedbackContract
    state: FeedbackOperationState
    message: str


@dataclass(frozen=True)
class PopupPresentationModel:
    title: str
    model: str
    source_preview: str
    pinned: bool
    back: bool
    contract: ActionFeedbackContract | None
    input_source: str
    guidance: bool
    enabled_actions: tuple[str, ...]
    speaking: bool
    feedback: PopupFeedbackModel | None


def project_popup_presentation(
    snapshot: SessionSnapshot,
    *,
    guidance_already_shown: bool = False,
) -> PopupPresentationModel:
    """Project Workflow state into the stable, content-free Popup interface."""
    displayed_step_id = _displayed_step_id(snapshot)
    feedback = None
    if (
        snapshot.status is SessionStatus.COMPLETED
        and snapshot.action_feedback_contract is not None
        and displayed_step_id is not None
    ):
        feedback = PopupFeedbackModel(
            displayed_step_id,
            snapshot.action_feedback_contract,
            snapshot.feedback_state,
            snapshot.feedback_message,
        )
    enabled_actions = snapshot.available_actions
    if snapshot.status is SessionStatus.CONTEXT_QUESTION:
        enabled_actions = tuple(
            action for action in enabled_actions if action != "follow_up"
        )
    return PopupPresentationModel(
        title=snapshot.title,
        model=snapshot.model,
        source_preview=_source_preview(snapshot),
        pinned=snapshot.pinned,
        back=snapshot.can_navigate_back,
        contract=snapshot.action_feedback_contract,
        input_source=snapshot.input_source,
        guidance=(
            snapshot.status is SessionStatus.COMPLETED
            and snapshot.show_guidance_hint
            and not guidance_already_shown
        ),
        enabled_actions=enabled_actions,
        speaking=snapshot.speaking,
        feedback=feedback,
    )


def _displayed_step_id(snapshot: SessionSnapshot) -> str | None:
    if 0 <= snapshot.displayed_step_index < len(snapshot.steps):
        return snapshot.steps[snapshot.displayed_step_index].step_id
    return None


def _source_preview(snapshot: SessionSnapshot) -> str:
    if snapshot.status is SessionStatus.FAILED and snapshot.content:
        return f"Failed: {snapshot.error}"
    if snapshot.status not in {
        SessionStatus.COMPLETED,
        SessionStatus.STOPPED,
        SessionStatus.CONTEXT_QUESTION,
        SessionStatus.VOICE_REVIEW,
    } and snapshot.content:
        return snapshot.status_text
    return snapshot.source_preview
