r"""Exercise real ClipAI text-widget mouse selection without a human operator.

Run on an interactive Windows desktop:
    .venv\Scripts\python.exe scripts\popup_text_selection_gate.py --repeat 3

Any selection mismatch exits nonzero. The fixture never reads or writes the
system clipboard or user text.
"""

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk

from ClipAI.services.presentation import MarkdownPresentationParser
from ClipAI.ui.base_dialog import (
    BaseResultSurface,
    _PresentationTextbox,
    install_script_aware_word_selection,
)


@dataclass(frozen=True)
class Verdict:
    case: str
    mode: str
    repeat: int
    expected: str
    actual: str | None
    passed: bool


def _point(text: tk.Text, index: str) -> tuple[int, int]:
    box = text.bbox(index)
    if box is None:
        raise RuntimeError(f"Text index {index} is not visible")
    x, y, _width, height = box
    return x + 1, y + height // 2


def _click(text: tk.Text, index: str, when: int) -> None:
    x, y = _point(text, index)
    text.event_generate("<ButtonPress-1>", x=x, y=y, time=when)
    text.event_generate("<ButtonRelease-1>", x=x, y=y, time=when + 40)
    text.update()


def _selection(text: tk.Text) -> str | None:
    try:
        return text.get("sel.first", "sel.last")
    except tk.TclError:
        return None


def _new_textbox(
    root: ctk.CTk,
    content: str,
    mode: str,
    *,
    script_aware: bool = True,
    block_ranges: Callable[[], tuple[tuple[int, int], ...]] | None = None,
) -> _PresentationTextbox:
    widget = _PresentationTextbox(root, width=540, height=180, wrap="word")
    widget.pack()
    widget.insert("1.0", content)
    if script_aware:
        install_script_aware_word_selection(widget, block_ranges=block_ranges)
    widget.configure(state=mode)
    root.update()
    return widget


def _run_case(root: ctk.CTk, case: str, mode: str, repeat: int, start: int) -> Verdict:
    if case == "context_menu_selection_only":
        surface = BaseResultSurface.__new__(BaseResultSurface)
        widget = _new_textbox(root, "alpha beta", mode)
        surface.content_text = widget
        surface._canonical_selection_segments = ()
        surface._install_content_context_menu()
        copied: list[str] = []
        surface.bind_content_context_copy(lambda: copied.append(surface.selected_text() or ""))
        text = widget._textbox
        x, y = _point(text, "1.7")
        _click(text, "1.7", start)
        _click(text, "1.7", start + 100)
        surface._content_context_menu.tk_popup = lambda _x, _y: None
        text.event_generate("<ButtonPress-3>", x=x, y=y, time=start + 250)
        root.update()
        enabled_when_selected = surface._content_context_menu.entrycget(0, "state")
        surface._content_context_menu.invoke(0)
        _click(text, "1.0", start + 2_000)
        text.event_generate("<ButtonPress-3>", x=x, y=y, time=start + 2_250)
        root.update()
        disabled_without_selection = surface._content_context_menu.entrycget(0, "state")
        surface._content_context_menu.invoke(0)
        surface._content_context_menu.invoke(1)
        actual = repr((enabled_when_selected, copied, disabled_without_selection, _selection(text)))
        expected = "('normal', ['beta'], 'disabled', 'alpha beta')"
        passed = actual == expected
    elif case == "copy_single_route":
        surface = BaseResultSurface.__new__(BaseResultSurface)
        widget = _new_textbox(root, "alpha beta", mode)
        surface.content_text = widget
        events: list[str] = []

        def routed_copy(_event) -> str:
            events.append("typed_copy")
            return "break"

        surface.bind_copy_shortcut(routed_copy)
        widget._textbox.bind("<<Copy>>", lambda _event: events.append("tk_copy"), add="+")
        root.bind("<Control-c>", lambda _event: events.append("root_copy"), add="+")
        widget._textbox.focus_set()
        root.update()
        widget._textbox.event_generate("<Control-c>", time=start)
        root.update()
        root.unbind("<Control-c>")
        actual = repr(events)
        expected = "['typed_copy']"
        passed = events == ["typed_copy"]
    elif case == "rendered_block":
        surface = BaseResultSurface.__new__(BaseResultSurface)
        surface._selection_block_ranges = ()
        widget = _new_textbox(
            root, "", "normal",
            block_ranges=lambda: surface._selection_block_ranges,
        )
        surface.content_text = widget
        surface._list_indent_prefixes = {}
        surface.set_presentation_document(
            MarkdownPresentationParser().parse(
                "# Title\n\nalpha beta\ngamma delta\n\n- item one"
            )
        )
        text = widget._textbox
        for index in range(3):
            _click(text, "2.7", start + index * 100)
        actual = surface.selected_text()
        expected = "alpha beta\ngamma delta\n"
        passed = actual == expected
    elif case == "voice_mode_transition":
        surface = BaseResultSurface.__new__(BaseResultSurface)
        surface._canonical_selection_segments = ()
        surface._selection_block_ranges = ()
        widget = _new_textbox(root, "", "normal")
        surface.content_text = widget
        surface.set_editable_content(
            "alpha beta\ngamma delta\n\nnext paragraph", lambda _text: None
        )
        text = widget._textbox
        selections: list[str | None] = []
        for phase in range(3):
            if phase == 1:
                surface.set_voice_draft_editing(False)
            elif phase == 2:
                surface.set_voice_draft_editing(True)
            root.update()
            for index in range(3):
                _click(text, "1.7", start + phase * 1_000 + index * 100)
            selections.append(surface.selected_text())
        expected = "alpha beta\ngamma delta\n in edit/read/edit"
        actual = repr(selections)
        passed = selections == ["alpha beta\ngamma delta\n"] * 3
    elif case == "double_word":
        widget = _new_textbox(root, "alpha beta gamma delta", mode)
        text = widget._textbox
        _click(text, "1.7", start)
        _click(text, "1.7", start + 100)
        actual = _selection(text)
        expected = "beta"
        passed = actual == expected
    elif case == "single_drag":
        widget = _new_textbox(root, "alpha beta gamma delta", mode)
        text = widget._textbox
        x1, y1 = _point(text, "1.0")
        x2, y2 = _point(text, "1.5")
        text.event_generate("<ButtonPress-1>", x=x1, y=y1, time=start)
        text.event_generate("<B1-Motion>", x=x2, y=y2, time=start + 100)
        root.update()
        actual = _selection(text)
        text.event_generate("<ButtonRelease-1>", x=x2, y=y2, time=start + 140)
        root.update()
        expected = "alpha"
        passed = actual == expected
    elif case == "shift_extend":
        widget = _new_textbox(root, "alpha beta gamma delta", mode)
        text = widget._textbox
        _click(text, "1.0", start)
        x, y = _point(text, "1.5")
        text.event_generate("<Shift-ButtonPress-1>", x=x, y=y, time=start + 100, state=0x0001)
        text.event_generate("<Shift-ButtonRelease-1>", x=x, y=y, time=start + 140, state=0x0001)
        root.update()
        actual = _selection(text)
        expected = "alpha"
        passed = actual == expected
    elif case in {"double_drag_word", "native_double_drag_word", "reverse_double_drag_word"}:
        widget = _new_textbox(
            root, "alpha beta gamma delta", mode,
            script_aware=case != "native_double_drag_word",
        )
        text = widget._textbox
        initial = "1.13" if case == "reverse_double_drag_word" else "1.7"
        target = "1.7" if case == "reverse_double_drag_word" else "1.13"
        _click(text, initial, start)
        _click(text, initial, start + 100)
        x, y = _point(text, target)
        text.event_generate("<B1-Motion>", x=x, y=y, time=start + 250)
        root.update()
        actual = _selection(text)
        text.event_generate("<ButtonRelease-1>", x=x, y=y, time=start + 290)
        root.update()
        expected = "beta gamma"
        passed = actual == expected
    elif case == "soft_wrap_paragraph":
        paragraph = "word " * 30
        widget = _new_textbox(root, paragraph + "\n\nnext", mode)
        text = widget._textbox
        for index in range(3):
            _click(text, "1.7", start + index * 100)
        actual = _selection(text)
        expected = paragraph + "\n"
        passed = actual == expected
    elif case in {"triple_paragraph", "native_triple_line"}:
        widget = _new_textbox(
            root, "alpha beta\ngamma delta\n\nnext paragraph", mode,
            script_aware=case == "triple_paragraph",
        )
        text = widget._textbox
        for index in range(3):
            _click(text, "1.7", start + index * 100)
        actual = _selection(text)
        if case == "native_triple_line":
            expected = "alpha beta\n"
            passed = actual == expected
        else:
            expected = "alpha beta\ngamma delta[optional final newline]"
            passed = actual in {"alpha beta\ngamma delta", "alpha beta\ngamma delta\n"}
    elif case == "triple_drag_paragraph":
        widget = _new_textbox(
            root, "alpha beta\ngamma delta\n\nnext paragraph", mode
        )
        text = widget._textbox
        for index in range(3):
            _click(text, "1.7", start + index * 100)
        x, y = _point(text, "4.6")
        text.event_generate("<B1-Motion>", x=x, y=y, time=start + 350)
        root.update()
        actual = _selection(text)
        text.event_generate("<ButtonRelease-1>", x=x, y=y, time=start + 390)
        expected = "alpha beta\ngamma delta\n\nnext paragraph"
        passed = actual == expected
    else:
        raise ValueError(case)

    widget.destroy()
    root.update()
    return Verdict(case, mode, repeat, expected, actual, passed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")

    root = ctk.CTk()
    root.geometry("600x230+100+100")
    root.attributes("-alpha", 0.0)
    root.update()
    verdicts: list[Verdict] = []
    try:
        for case in (
            "native_triple_line", "native_double_drag_word",
            "double_word", "single_drag", "shift_extend",
            "triple_paragraph", "triple_drag_paragraph", "soft_wrap_paragraph",
            "double_drag_word", "reverse_double_drag_word",
            "rendered_block", "voice_mode_transition", "copy_single_route",
            "context_menu_selection_only",
        ):
            for repetition in range(args.repeat):
                modes = ("normal", "disabled") if case not in {
                    "rendered_block", "voice_mode_transition"
                } else ("lifecycle",)
                for mode in modes:
                    start = 10_000 + len(verdicts) * 2_000
                    verdicts.append(_run_case(root, case, mode, repetition + 1, start))
    finally:
        root.destroy()

    for verdict in verdicts:
        print(json.dumps(verdict.__dict__, ensure_ascii=False))
    failures = sum(not verdict.passed for verdict in verdicts)
    print(json.dumps({"cases": len(verdicts), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
