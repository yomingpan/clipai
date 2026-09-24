"""Keyboard ownership at the inline dictation choice boundary."""

import tkinter as tk

import pytest

from ClipAI.ui.inline_dictation import InlineDictationWindow


@pytest.mark.integration
def test_choice_activates_its_native_window_before_accepting_shortcuts() -> None:
    class NativeSurface:
        def __init__(self) -> None:
            self.activated_window_id: int | None = None

        def activate(self, window_id: int) -> bool:
            self.activated_window_id = window_id
            return True

    root = tk.Tk()
    root.withdraw()
    native = NativeSurface()
    confirmations: list[bool] = []
    try:
        for shortcut, refine in (("<Return>", False), ("<Control-p>", True)):
            window = InlineDictationWindow(
                root,
                on_confirm=confirmations.append,
                on_cancel=lambda: None,
                native_window_surface=native,
            )
            try:
                window.show()
                root.update()

                window.present_choice("recognized words")
                root.update()

                assert native.activated_window_id == window._window.winfo_id()
                assert root.focus_get() is window._window
                window._window.event_generate(shortcut)
                root.update()
                assert confirmations[-1] is refine
            finally:
                window.close()
    finally:
        root.destroy()
