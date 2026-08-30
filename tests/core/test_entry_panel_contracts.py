from dataclasses import FrozenInstanceError

import pytest

from ClipAI.core.models import ActionStartAdmission, EntryActionRef


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
