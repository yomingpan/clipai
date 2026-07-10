from __future__ import annotations


class SystemKeyboardOutput:
    def paste(self) -> None:
        from pynput.keyboard import Controller, Key

        keyboard = Controller()
        with keyboard.pressed(Key.ctrl):
            keyboard.press("v")
            keyboard.release("v")
