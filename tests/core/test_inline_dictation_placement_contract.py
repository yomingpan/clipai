from __future__ import annotations

from ClipAI.core.commands import InlineDictationPlacementPreferencesCompleted, SetInlineDictationPlacement
from ClipAI.core.models import InlineDictationPlacementState, UserPreferences


def test_inline_dictation_placement_contract_defaults_to_cursor() -> None:
    assert UserPreferences().inline_dictation_placement == "cursor"
    assert InlineDictationPlacementState().selected_placement == "cursor"
    assert SetInlineDictationPlacement("bottom_center").operation_id == ""
    assert InlineDictationPlacementPreferencesCompleted("operation-1").error == ""
