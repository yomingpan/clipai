from dataclasses import FrozenInstanceError
import inspect

import pytest

from ClipAI.core.commands import ShortcutPressThresholdReached
from ClipAI.core.models import ShortcutPressId
from ClipAI.core.ports import InlineDictationPresenter
from ClipAI.platform.native_window import HeadlessNativeWindowSurface


def test_threshold_notification_is_immutable_and_retains_the_press_identity():
    event = ShortcutPressThresholdReached(ShortcutPressId(7), "inline_dictation")
    assert event.press_id == 7
    assert event.shortcut_id == "inline_dictation"
    with pytest.raises(FrozenInstanceError):
        event.press_id = ShortcutPressId(8)


def test_inline_presenter_exposes_only_lifecycle_and_one_complete_view():
    methods = {name for name, value in inspect.getmembers(InlineDictationPresenter, inspect.isfunction) if not name.startswith("_")}
    assert methods == {"open_inline_dictation", "present_inline_dictation", "close_inline_dictation"}
    assert tuple(inspect.signature(InlineDictationPresenter.open_inline_dictation).parameters) == (
        "self", "interaction_id", "mode",
    )


def test_headless_native_ports_never_claim_activation_or_screen_capture():
    surface = HeadlessNativeWindowSurface()
    assert surface.prevent_click_activation(10) is False
    assert surface.capture_screen_rgb(0, 0, 132, 26) is None
