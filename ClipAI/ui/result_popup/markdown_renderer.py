from __future__ import annotations

import re
import tkinter as tk
from typing import Any


_LIST_PATTERN = re.compile(r"^(\-|\*|\d+\.)\s+(.*)$")
_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.*)$")
_INLINE_PATTERN = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


class PopupMarkdownRenderer:
    BODY_FONT = ("Microsoft JhengHei", 11)
    HEADING_FONT = ("Microsoft JhengHei UI", 12, "bold")
    META_FONT = ("Microsoft JhengHei", 10)
    CODE_FONT = ("Consolas", 10)
    LIST_INDENT = 22

    @staticmethod
    def format_input_preview(text: str, max_chars: int = 58) -> str:
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
    def source_label_for_session(session: Any) -> str:
        state = session.snapshot() if hasattr(session, "snapshot") else session
        provider = str(getattr(state, "current_provider", "") or "").strip()
        model = str(getattr(state, "current_model", "") or "").strip()
        if provider and model:
            return f"{provider} | {model}"
        return model or provider

    @staticmethod
    def render_session_text(text_widget: tk.Text, session: Any) -> None:
        state = session.snapshot() if hasattr(session, "snapshot") else session
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        PopupMarkdownRenderer._configure_tags(text_widget)

        normalized = PopupMarkdownRenderer.normalize_content(
            PopupMarkdownRenderer.result_text_for_session(state).strip()
        )
        PopupMarkdownRenderer.insert_markdown(text_widget, normalized or " ", style="body")

        if state.rounds:
            for item in state.rounds:
                text_widget.insert("end", "\n", ("history_body",))
                round_label = "Deep Think" if item.kind == "deep_think" else "Follow-up"
                text_widget.insert("end", f"Round {item.round_index} | {round_label}\n", ("history_label",))

                prompt = PopupMarkdownRenderer.normalize_content(item.prompt_text.strip())
                if prompt:
                    PopupMarkdownRenderer.insert_markdown(text_widget, prompt, style="history")

                result_text = PopupMarkdownRenderer.normalize_content(item.result_text.strip())
                if result_text:
                    text_widget.insert("end", "\n", ("history_body",))
                    PopupMarkdownRenderer.insert_markdown(text_widget, result_text, style="history")

        text_widget.config(state="disabled")

    @staticmethod
    def normalize_content(content: str) -> str:
        text = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""

        raw_lines = [
            re.sub(r"^(\s*)([\-\*]|\d+\.)\s+", r"\1- ", line.rstrip())
            for line in text.split("\n")
        ]

        normalized_lines: list[str] = []
        previous_blank = False

        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                if normalized_lines and _HEADING_PATTERN.match(normalized_lines[-1]):
                    continue
                if previous_blank:
                    continue
                normalized_lines.append("")
                previous_blank = True
                continue

            if _HEADING_PATTERN.match(line) and normalized_lines:
                previous_line = normalized_lines[-1]
                if previous_line.strip() and not _HEADING_PATTERN.match(previous_line):
                    normalized_lines.append("")

            normalized_lines.append(line)
            previous_blank = False

        compacted: list[str] = []
        for line in normalized_lines:
            if compacted and compacted[-1] == "" and _HEADING_PATTERN.match(line):
                compacted.pop()
            compacted.append(line)

        return "\n".join(compacted).strip()

    @staticmethod
    def code_tag_palette(text_widget: tk.Text) -> tuple[str, str]:
        background = str(text_widget.cget("bg") or "").strip()
        if background.startswith("#") and len(background) == 7:
            red = int(background[1:3], 16)
            green = int(background[3:5], 16)
            blue = int(background[5:7], 16)
            luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
            if luminance < 128:
                return "#253041", "#EEF4FF"
        return "#EEF3F8", "#1F2937"

    @staticmethod
    def _configure_tags(text_widget: tk.Text) -> None:
        code_bg, code_fg = PopupMarkdownRenderer.code_tag_palette(text_widget)
        palette = PopupMarkdownRenderer._text_palette(text_widget)

        text_widget.tag_configure(
            "body",
            font=PopupMarkdownRenderer.BODY_FONT,
            spacing1=1,
            spacing3=3,
            foreground=palette["body_text"],
        )
        text_widget.tag_configure(
            "body_heading",
            font=PopupMarkdownRenderer.HEADING_FONT,
            foreground=palette["body_heading"],
            spacing1=4,
            spacing3=5,
        )
        text_widget.tag_configure(
            "body_bold",
            font=("Microsoft JhengHei UI", 11, "bold"),
            foreground=palette["body_text"],
        )
        text_widget.tag_configure(
            "body_code",
            font=PopupMarkdownRenderer.CODE_FONT,
            background=code_bg,
            foreground=code_fg,
        )
        text_widget.tag_configure(
            "body_quote",
            foreground=palette["body_quote"],
            lmargin1=14,
            lmargin2=14,
            spacing1=1,
            spacing3=3,
        )
        text_widget.tag_configure(
            "body_list_marker",
            font=PopupMarkdownRenderer.BODY_FONT,
            foreground=palette["body_marker"],
        )
        text_widget.tag_configure(
            "body_list_text",
            font=PopupMarkdownRenderer.BODY_FONT,
            foreground=palette["body_text"],
            lmargin1=PopupMarkdownRenderer.LIST_INDENT,
            lmargin2=PopupMarkdownRenderer.LIST_INDENT,
            spacing1=1,
            spacing3=3,
        )

        text_widget.tag_configure(
            "history_body",
            font=PopupMarkdownRenderer.BODY_FONT,
            foreground=palette["history_text"],
            spacing1=1,
            spacing3=3,
        )
        text_widget.tag_configure(
            "history_heading",
            font=PopupMarkdownRenderer.HEADING_FONT,
            foreground=palette["history_heading"],
            spacing1=4,
            spacing3=5,
        )
        text_widget.tag_configure(
            "history_bold",
            font=("Microsoft JhengHei UI", 11, "bold"),
            foreground=palette["history_heading"],
        )
        text_widget.tag_configure(
            "history_code",
            font=PopupMarkdownRenderer.CODE_FONT,
            background=code_bg,
            foreground=palette["history_heading"],
        )
        text_widget.tag_configure(
            "history_quote",
            foreground=palette["history_quote"],
            lmargin1=14,
            lmargin2=14,
            spacing1=1,
            spacing3=3,
        )
        text_widget.tag_configure(
            "history_list_marker",
            font=PopupMarkdownRenderer.BODY_FONT,
            foreground=palette["history_marker"],
        )
        text_widget.tag_configure(
            "history_list_text",
            font=PopupMarkdownRenderer.BODY_FONT,
            foreground=palette["history_text"],
            lmargin1=PopupMarkdownRenderer.LIST_INDENT,
            lmargin2=PopupMarkdownRenderer.LIST_INDENT,
            spacing1=1,
            spacing3=3,
        )
        text_widget.tag_configure(
            "history_label",
            font=PopupMarkdownRenderer.META_FONT,
            foreground=palette["history_label"],
            spacing1=2,
            spacing3=2,
        )

    @staticmethod
    def _text_palette(text_widget: tk.Text) -> dict[str, str]:
        background = str(text_widget.cget("bg") or "").strip()
        if background.startswith("#") and len(background) == 7:
            red = int(background[1:3], 16)
            green = int(background[3:5], 16)
            blue = int(background[5:7], 16)
            luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
            if luminance < 128:
                return {
                    "body_text": "#F3F6FB",
                    "body_heading": "#AFCBFF",
                    "body_marker": "#C9DAF7",
                    "body_quote": "#AAB7C9",
                    "history_text": "#AEB8C6",
                    "history_heading": "#C3CDD9",
                    "history_marker": "#B8C3D3",
                    "history_quote": "#9DAABC",
                    "history_label": "#94A3B8",
                }
        return {
            "body_text": "#1F2937",
            "body_heading": "#163A70",
            "body_marker": "#315A8B",
            "body_quote": "#64748B",
            "history_text": "#6B7280",
            "history_heading": "#4B5563",
            "history_marker": "#6B7280",
            "history_quote": "#7C8898",
            "history_label": "#7B8794",
        }

    @staticmethod
    def insert_markdown(text_widget: tk.Text, content: str, style: str = "body") -> None:
        normalized = PopupMarkdownRenderer.normalize_content(content)
        if not normalized:
            return

        for raw_line in normalized.splitlines():
            line = raw_line.rstrip()
            if not line:
                text_widget.insert("end", "\n", (f"{style}_body",))
                continue

            heading_match = _HEADING_PATTERN.match(line)
            if heading_match:
                heading_text = heading_match.group(2).strip()
                PopupMarkdownRenderer.insert_inline_markdown(
                    text_widget, heading_text, style, line_kind="heading"
                )
                text_widget.insert("end", "\n")
                continue

            list_match = _LIST_PATTERN.match(line)
            if list_match:
                text_widget.insert("end", "• ", (f"{style}_list_marker",))
                PopupMarkdownRenderer.insert_inline_markdown(
                    text_widget, list_match.group(2).strip(), style, line_kind="list"
                )
                text_widget.insert("end", "\n")
                continue

            if line.startswith("> "):
                PopupMarkdownRenderer.insert_inline_markdown(
                    text_widget, line[2:].strip(), style, line_kind="quote"
                )
                text_widget.insert("end", "\n")
                continue

            PopupMarkdownRenderer.insert_inline_markdown(text_widget, line, style, line_kind="body")
            text_widget.insert("end", "\n")

    @staticmethod
    def insert_inline_markdown(
        text_widget: tk.Text,
        line: str,
        style: str,
        line_kind: str = "body",
    ) -> None:
        base_tag = PopupMarkdownRenderer._base_tag(style, line_kind)
        bold_tag = f"{style}_bold"
        code_tag = f"{style}_code"
        cursor = 0

        for match in _INLINE_PATTERN.finditer(line):
            if match.start() > cursor:
                text_widget.insert("end", line[cursor:match.start()], (base_tag,))
            token = match.group(0)
            if token.startswith("**") and token.endswith("**"):
                text_widget.insert("end", token[2:-2], (base_tag, bold_tag))
            elif token.startswith("`") and token.endswith("`"):
                text_widget.insert("end", token[1:-1], (base_tag, code_tag))
            cursor = match.end()

        if cursor < len(line):
            text_widget.insert("end", line[cursor:], (base_tag,))

    @staticmethod
    def _base_tag(style: str, line_kind: str) -> str:
        if line_kind == "heading":
            return f"{style}_heading"
        if line_kind == "quote":
            return f"{style}_quote"
        if line_kind == "list":
            return f"{style}_list_text"
        return f"{style}_body"
