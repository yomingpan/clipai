from __future__ import annotations

from ClipAI.core.commands import InlineDictationPlacementPreferencesCompleted, SetInlineDictationPlacement
from ClipAI.core.models import InlineDictationPlacementState, UserPreferences


def test_inline_dictation_placement_contract_defaults_to_bottom_center() -> None:
    assert UserPreferences().inline_dictation_placement == "bottom_center"
    assert InlineDictationPlacementState().selected_placement == "bottom_center"
    assert SetInlineDictationPlacement("bottom_center").operation_id == ""
    assert InlineDictationPlacementPreferencesCompleted("operation-1").error == ""
