from __future__ import annotations

import re

from ClipAI.core.models import InlineSpan, PresentationBlock, PresentationDocument

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_UNORDERED = re.compile(r"^([-+*])\s+(.+)$")
_ORDERED = re.compile(r"^(\d+)[.)]\s+(.+)$")
_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|__[^_\n]+__|(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_))")


class MarkdownPresentationParser:
    """Parse the deliberately small Markdown subset supported by the popup."""

    def parse(self, text: str) -> PresentationDocument:
        blocks: list[PresentationBlock] = []
        paragraph: list[str] = []

        def flush_paragraph() -> None:
            if paragraph:
                blocks.append(PresentationBlock("paragraph", self._inline("\n".join(paragraph))))
                paragraph.clear()

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                flush_paragraph()
                continue
            if line[:1].isspace():
                paragraph.append(line.strip())
                continue
            heading = _HEADING.match(line)
            unordered = _UNORDERED.match(line)
            ordered = _ORDERED.match(line)
            if heading:
                flush_paragraph()
                blocks.append(PresentationBlock("heading", self._inline(heading.group(2)), len(heading.group(1))))
            elif unordered:
                flush_paragraph()
                blocks.append(PresentationBlock("unordered_item", self._inline(unordered.group(2))))
            elif ordered:
                flush_paragraph()
                blocks.append(PresentationBlock("ordered_item", self._inline(ordered.group(2)), ordinal=int(ordered.group(1))))
            else:
                paragraph.append(line)
        flush_paragraph()
        if not blocks and text:
            blocks.append(PresentationBlock("paragraph", (InlineSpan(text),)))
        return PresentationDocument(tuple(blocks), text)

    @staticmethod
    def _inline(text: str) -> tuple[InlineSpan, ...]:
        spans: list[InlineSpan] = []
        cursor = 0
        for match in _INLINE.finditer(text):
            if match.start() > cursor:
                spans.append(InlineSpan(text[cursor : match.start()]))
            token = match.group(0)
            if token.startswith(("**", "__")):
                spans.append(InlineSpan(token[2:-2], "bold"))
            else:
                spans.append(InlineSpan(token[1:-1], "italic"))
            cursor = match.end()
        if cursor < len(text):
            spans.append(InlineSpan(text[cursor:]))
        return tuple(spans) or (InlineSpan(""),)
