from dataclasses import FrozenInstanceError

import pytest

from ClipAI.core.voice import InlineDictationView


def test_inline_view_is_an_immutable_identity_scoped_projection():
    view = InlineDictationView("i-1", phase="listening", text="canonical content")
    assert view.interaction_id == "i-1"
    assert view.chosen is None
    assert view.copy_state == "idle"
    assert view.preview_refine is False
    with pytest.raises(FrozenInstanceError):
        view.phase = "pasting"
    assert "canonical content" not in repr(view)
