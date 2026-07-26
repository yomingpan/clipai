from __future__ import annotations

from collections.abc import Callable
import time

from ClipAI.platform.keyboard_state import MODIFIER_KEYS, windows_modifier_is_pressed


class SystemKeyboardOutput:
    def __init__(
        self,
        *,
        modifier_is_pressed: Callable[[str], bool | None] = windows_modifier_is_pressed,
        modifier_release_timeout_sec: float = 1.0,
        poll_sec: float = 0.02,
        wait: Callable[[float], None] = time.sleep,
        paste_shortcut: Callable[[], None] | None = None,
    ) -> None:
        self._modifier_is_pressed = modifier_is_pressed
        self._modifier_release_timeout_sec = modifier_release_timeout_sec
        self._poll_sec = poll_sec
        self._wait = wait
        self._paste_shortcut = paste_shortcut or _send_paste_shortcut

    def paste(self) -> None:
        deadline = time.monotonic() + self._modifier_release_timeout_sec
        while any(self._modifier_is_pressed(modifier) is True for modifier in MODIFIER_KEYS):
            if time.monotonic() >= deadline:
                raise RuntimeError("Keyboard modifiers were not released in time.")
            self._wait(self._poll_sec)
        self._paste_shortcut()


def _send_paste_shortcut() -> None:
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("v")
        keyboard.release("v")
