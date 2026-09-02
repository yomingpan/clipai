from dataclasses import FrozenInstanceError

import pytest

from ClipAI.core.commands import EntryPanelInputPreparationCompleted
from ClipAI.core.models import (
    ActionStartAdmission,
    EntryActionRef,
    EntryInputPreparationId,
    InputDocument,
    PreparedEntryInput,
)


def test_entry_action_reference_preserves_explicit_press_variant() -> None:
    candidate = EntryActionRef("english_companion", "long")

    assert candidate.action_id == "english_companion"
    assert candidate.press_type == "long"
    with pytest.raises(FrozenInstanceError):
        candidate.press_type = "short"  # type: ignore[misc]


def test_action_start_admission_carries_authoritative_rejection() -> None:
    admission = ActionStartAdmission(
        "blocked",
        reason="voice_active",
        message="請先停止語音輸入",
    )

    assert admission.accepted is False
    assert admission.reason == "voice_active"
    assert admission.message == "請先停止語音輸入"


def test_accepted_action_admission_identifies_the_authoritative_workflow() -> None:
    admission = ActionStartAdmission("accepted", workflow_id="workflow-1")

    assert admission.accepted is True
    assert admission.workflow_id == "workflow-1"

    with pytest.raises(ValueError, match="requires workflow_id"):
        ActionStartAdmission("accepted")


def test_preparation_completion_repr_does_not_expose_frozen_input() -> None:
    command = EntryPanelInputPreparationCompleted(
        "panel-1",
        EntryInputPreparationId("preparation-1"),
        PreparedEntryInput(
            selection_document=InputDocument("private text", "selection")
        ),
    )

    assert "private text" not in repr(command)
