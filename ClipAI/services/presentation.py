from __future__ import annotations

import re
from typing import Literal

from ClipAI.core.models import InlineSpan, PresentationBlock, PresentationDocument

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_UNORDERED = re.compile(r"^([-+*])\s+(.+)$")
_ORDERED = re.compile(r"^(\d+)[.)]\s+(.+)$")
_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|__[^_\n]+__|(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_))")
_SCROLL_FOR_ANSWER = "[[SCROLL_FOR_ANSWER]]"
_SCROLL_GAP_LINES = 8


class MarkdownPresentationParser:
    """Parse the deliberately small Markdown subset supported by the popup."""

    def parse(self, text: str) -> PresentationDocument:
        blocks: list[PresentationBlock] = []
        paragraph: list[str] = []
        pending_list_item: tuple[Literal["unordered_item", "ordered_item"], int | None, list[str]] | None = None

        def flush_paragraph() -> None:
            if paragraph:
                blocks.append(PresentationBlock("paragraph", self._inline("\n".join(paragraph))))
                paragraph.clear()

        def flush_list_item() -> None:
            nonlocal pending_list_item
            if pending_list_item is None:
                return
            kind, ordinal, lines = pending_list_item
            prefix = "- " if kind == "unordered_item" else f"{ordinal or 1}. "
            blocks.append(PresentationBlock(
                kind,
                self._inline("\n".join(lines), continuation_indent="  "),
                ordinal=ordinal,
                canonical_prefix=prefix,
            ))
            pending_list_item = None

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                flush_list_item()
                flush_paragraph()
                continue
            if line[:1].isspace():
                if pending_list_item is not None:
                    pending_list_item[2].append(line.strip())
                else:
                    paragraph.append(line.strip())
                continue
            if line.strip() == _SCROLL_FOR_ANSWER:
                flush_list_item()
                flush_paragraph()
                blocks.append(PresentationBlock(
                    "spacer",
                    (InlineSpan("\n" * _SCROLL_GAP_LINES, canonical_text=""),),
                ))
                continue
            heading = _HEADING.match(line)
            unordered = _UNORDERED.match(line)
            ordered = _ORDERED.match(line)
            if heading:
                flush_list_item()
                flush_paragraph()
                level = len(heading.group(1))
                blocks.append(PresentationBlock(
                    "heading",
                    self._inline(heading.group(2)),
                    level,
                    canonical_prefix=f"{'#' * level} ",
                ))
            elif unordered:
                flush_list_item()
                flush_paragraph()
                pending_list_item = ("unordered_item", None, [unordered.group(2)])
            elif ordered:
                flush_list_item()
                flush_paragraph()
                pending_list_item = ("ordered_item", int(ordered.group(1)), [ordered.group(2)])
            else:
                flush_list_item()
                paragraph.append(line)
        flush_list_item()
        flush_paragraph()
        if not blocks and text:
            blocks.append(PresentationBlock("paragraph", (InlineSpan(text),)))
        fallback_text = "\n".join(
            line for line in text.splitlines() if line.strip() != _SCROLL_FOR_ANSWER
        )
        return PresentationDocument(tuple(blocks), fallback_text)

    @staticmethod
    def _inline(text: str, *, continuation_indent: str = "") -> tuple[InlineSpan, ...]:
        spans: list[InlineSpan] = []
        cursor = 0
        for match in _INLINE.finditer(text):
            if match.start() > cursor:
                plain = text[cursor : match.start()]
                canonical = plain.replace("\n", f"\n{continuation_indent}") if continuation_indent else None
                spans.append(InlineSpan(plain, canonical_text=canonical))
            token = match.group(0)
            if token.startswith(("**", "__")):
                spans.append(InlineSpan(token[2:-2], "bold", token))
            else:
                spans.append(InlineSpan(token[1:-1], "italic", token))
            cursor = match.end()
        if cursor < len(text):
            plain = text[cursor:]
            canonical = plain.replace("\n", f"\n{continuation_indent}") if continuation_indent else None
            spans.append(InlineSpan(plain, canonical_text=canonical))
        return tuple(spans) or (InlineSpan(""),)
