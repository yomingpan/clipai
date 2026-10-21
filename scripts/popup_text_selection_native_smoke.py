"""Verify Popup multi-click selection with real Windows mouse input.

Requires an interactive Windows desktop. It aborts before moving the pointer
unless its original position and the test window's foreground ownership are
confirmed. The original pointer position is restored in ``finally``.
"""

from __future__ import annotations

import json
import sys
import time
import tkinter as tk

import customtkinter as ctk
from pynput.mouse import Button, Controller

from ClipAI.platform.native_window import WindowsNativeWindowSurface
from ClipAI.ui.base_dialog import (
    _PresentationTextbox,
    install_script_aware_word_selection,
)


def _selected(text: tk.Text) -> str | None:
    try:
        return text.get("sel.first", "sel.last")
    except tk.TclError:
        return None


def main() -> int:
    mouse = Controller()
    original_position = mouse.position
    if original_position is None:
        print(json.dumps({"error": "cursor_position_unavailable"}))
        return 2

    native = WindowsNativeWindowSurface()
    root = ctk.CTk()
    root.geometry("600x230+250+250")
    root.attributes("-topmost", True)
    results: list[dict[str, object]] = []
    try:
        for mode in ("normal", "disabled"):
            widget = _PresentationTextbox(root, width=540, height=180, wrap="word")
            widget.pack()
            widget.insert("1.0", "alpha beta gamma delta\nsecond line\n\nnext paragraph")
            install_script_aware_word_selection(widget)
            widget.configure(state=mode)
            root.update()
            text = widget._textbox
            text.focus_force()
            root.update()
            shell_id = root.winfo_id()
            owns_before = native.owns_foreground(shell_id)
            activated = native.activate(shell_id)
            owns_after = native.owns_foreground(shell_id)
            if not activated or not owns_after:
                raise RuntimeError(
                    f"test_window_not_foreground: before={owns_before}, "
                    f"activated={activated}, after={owns_after}"
                )
            box = text.bbox("1.7")
            if box is None:
                raise RuntimeError("test_text_not_visible")
            x, y, _width, height = box
            mouse.position = (
                text.winfo_rootx() + x + 1,
                text.winfo_rooty() + y + height // 2,
            )
            time.sleep(0.08)
            if not native.owns_foreground(shell_id):
                raise RuntimeError("test_window_lost_foreground")
            actual: list[str | None] = []
            for _ in range(3):
                mouse.press(Button.left)
                mouse.release(Button.left)
                time.sleep(0.09)
                root.update()
                actual.append(_selected(text))
            expected = [None, "beta", "alpha beta gamma delta\nsecond line\n"]
            results.append({
                "case": "triple_paragraph", "mode": mode,
                "expected": expected, "actual": actual, "passed": actual == expected,
            })
            time.sleep(0.6)
            if not native.owns_foreground(shell_id):
                raise RuntimeError("test_window_lost_foreground_before_drag")
            origin = text.bbox("1.7")
            target = text.bbox("1.13")
            if origin is None or target is None:
                raise RuntimeError("drag_text_not_visible")
            start_point = (
                text.winfo_rootx() + origin[0] + 1,
                text.winfo_rooty() + origin[1] + origin[3] // 2,
            )
            end_point = (
                text.winfo_rootx() + target[0] + 1,
                text.winfo_rooty() + target[1] + target[3] // 2,
            )
            mouse.position = start_point
            time.sleep(0.08)
            mouse.press(Button.left)
            mouse.release(Button.left)
            time.sleep(0.09)
            root.update()
            mouse.press(Button.left)
            mouse.position = end_point
            time.sleep(0.12)
            root.update()
            dragged = _selected(text)
            mouse.release(Button.left)
            results.append({
                "case": "double_drag_word", "mode": mode,
                "expected": "beta gamma", "actual": dragged,
                "passed": dragged == "beta gamma",
            })
            widget.destroy()
            root.update()
            time.sleep(0.6)
    except Exception as exc:
        print(json.dumps({"error": str(exc), "results": results}, ensure_ascii=False))
        return 2
    finally:
        mouse.position = original_position
        root.destroy()

    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
