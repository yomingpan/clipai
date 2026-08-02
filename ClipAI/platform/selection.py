from __future__ import annotations

from collections.abc import Callable

from ClipAI.platform.keyboard_state import windows_modifier_is_pressed


class SystemSelectionCaptureAdapter:
    """OS primitives used by the service-owned selection transaction."""

    def __init__(
        self,
        *,
        copy_selection: Callable[[], None] | None = None,
        modifier_is_pressed: Callable[[str], bool | None] = windows_modifier_is_pressed,
    ) -> None:
        self._copy_selection = copy_selection or _send_copy_shortcut
        self._modifier_is_pressed = modifier_is_pressed

    def modifier_is_pressed(self, modifier: str) -> bool | None:
        return self._modifier_is_pressed(modifier)

    def copy_selection(self) -> None:
        self._copy_selection()


def _send_copy_shortcut() -> None:
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("c")
        keyboard.release("c")
