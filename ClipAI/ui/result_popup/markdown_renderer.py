from __future__ import annotations

import re
import tkinter as tk
from typing import Any


class PopupMarkdownRenderer:
    @staticmethod
    def format_input_preview(text: str, max_chars: int = 88) -> str:
        compact = " ".join((text or "").split())
        if not compact:
            return "Analysis: (empty input)"
        if len(compact) > max_chars:
            compact = compact[: max_chars - 3].rstrip() + "..."
        return f"Analysis: {compact}"

    @staticmethod
    def input_preview_for_session(session: Any) -> str:
        if session.input_loading:
            return "Analysis: Connecting..."
        return PopupMarkdownRenderer.format_input_preview(session.original_input)

    @staticmethod
    def result_text_for_session(session: Any) -> str:
        if session.result_loading and not session.latest_result.strip():
            return "Connecting..."
        return session.latest_result

    @staticmethod
    def render_session_text(text_widget: tk.Text, session: Any) -> None:
        state = session.snapshot() if hasattr(session, "snapshot") else session
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        code_bg, code_fg = PopupMarkdownRenderer.code_tag_palette(text_widget)
        text_widget.tag_configure("body", spacing1=2, spacing3=3)
        text_widget.tag_configure("history", foreground="#7A7F87")
        text_widget.tag_configure("md_h1", font=("Microsoft JhengHei", 14, "bold"), spacing1=6, spacing3=4)
        text_widget.tag_configure("md_h2", font=("Microsoft JhengHei", 13, "bold"), spacing1=5, spacing3=3)
        text_widget.tag_configure("md_h3", font=("Microsoft JhengHei", 12, "bold"), spacing1=4, spacing3=3)
        text_widget.tag_configure("md_h4", font=("Microsoft JhengHei", 11, "bold"), spacing1=3, spacing3=2)
        text_widget.tag_configure("md_bold", font=("Microsoft JhengHei", 11, "bold"))
        text_widget.tag_configure("md_code", font=("Consolas", 10), background=code_bg, foreground=code_fg)
        text_widget.tag_configure("md_quote", foreground="#94A3B8", lmargin1=16, lmargin2=16, spacing1=2, spacing3=2)
        PopupMarkdownRenderer.insert_markdown(
            text_widget,
            PopupMarkdownRenderer.result_text_for_session(state).strip() or " ",
            base_tag="body",
        )
        if state.rounds:
            for item in state.rounds:
                text_widget.insert("end", f"\n\n--- round {item.round_index} ---\n", ("history",))
                label = "Deep Think" if item.kind == "deep_think" else "Follow-up"
                text_widget.insert("end", f"{label}: {item.prompt_text.strip()}\n", ("history",))
                PopupMarkdownRenderer.insert_markdown(text_widget, item.result_text.strip(), base_tag="history")
        text_widget.config(state="disabled")

    @staticmethod
    def code_tag_palette(text_widget: tk.Text) -> tuple[str, str]:
        background = str(text_widget.cget("bg") or "").strip()
        if background.startswith("#") and len(background) == 7:
            red = int(background[1:3], 16)
            green = int(background[3:5], 16)
            blue = int(background[5:7], 16)
            luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
            if luminance < 128:
                return "#2C3442", "#F7FAFF"
        return "#EEF3F8", "#1F2937"

    @staticmethod
    def insert_markdown(text_widget: tk.Text, content: str, base_tag: str = "body") -> None:
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line:
                text_widget.insert("end", "\n", (base_tag,))
                continue

            heading_match = re.match(r"^(#{1,4})\s+(.*)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2)
                heading_tag = {
                    1: "md_h1",
                    2: "md_h2",
                    3: "md_h3",
                    4: "md_h4",
                }.get(level, "md_h4")
                PopupMarkdownRenderer.insert_inline_markdown(text_widget, heading_text, (heading_tag,))
                text_widget.insert("end", "\n")
                continue
            if re.match(r"^(\-|\*|\d+\.)\s+", line):
                normalized = re.sub(r"^(\-|\*|\d+\.)\s+", "- ", line, count=1)
                PopupMarkdownRenderer.insert_inline_markdown(text_widget, normalized, (base_tag,))
                text_widget.insert("end", "\n")
                continue
            if line.startswith("> "):
                PopupMarkdownRenderer.insert_inline_markdown(text_widget, line[2:], (base_tag, "md_quote"))
                text_widget.insert("end", "\n")
                continue

            PopupMarkdownRenderer.insert_inline_markdown(text_widget, line, (base_tag,))
            text_widget.insert("end", "\n")

    @staticmethod
    def insert_inline_markdown(text_widget: tk.Text, line: str, base_tags: tuple[str, ...]) -> None:
        pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
        cursor = 0
        for match in pattern.finditer(line):
            if match.start() > cursor:
                text_widget.insert("end", line[cursor:match.start()], base_tags)
            token = match.group(0)
            if token.startswith("**") and token.endswith("**"):
                text_widget.insert("end", token[2:-2], base_tags + ("md_bold",))
            elif token.startswith("`") and token.endswith("`"):
                text_widget.insert("end", token[1:-1], base_tags + ("md_code",))
            cursor = match.end()
        if cursor < len(line):
            text_widget.insert("end", line[cursor:], base_tags)
