from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ClipAI.core.models import PresentationDocument
from ClipAI.ui.text_layout import DISPLAY_BREAK_HINT, add_display_break_hints, display_break_opportunity


RenderStepKind = Literal["indent", "text", "break_hint", "newline"]


@dataclass(frozen=True)
class RenderSelectionSegment:
    offset: int
    display_text: str
    canonical_text: str

    @property
    def end(self) -> int:
        return self.offset + len(self.display_text)


@dataclass(frozen=True)
class RenderStep:
    kind: RenderStepKind
    text: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class PopupRenderPlan:
    steps: tuple[RenderStep, ...]
    selection_segments: tuple[RenderSelectionSegment, ...]
    indent_prefixes: tuple[tuple[str, str], ...]


def build_popup_render_plan(document: PresentationDocument) -> PopupRenderPlan:
    steps: list[RenderStep] = []
    segments: list[RenderSelectionSegment] = []
    indent_prefixes: list[tuple[str, str]] = []
    offset = 0

    def record(display_text: str, canonical_text: str) -> None:
        nonlocal offset
        if not display_text:
            return
        segments.append(RenderSelectionSegment(offset, display_text, canonical_text))
        offset += len(display_text)

    def emit(kind: Literal["indent", "text"], value: str, tags: tuple[str, ...]) -> None:
        parts = add_display_break_hints(value).split(DISPLAY_BREAK_HINT)
        for index, part in enumerate(parts):
            if part:
                steps.append(RenderStep(kind, part, tags))
            if index + 1 < len(parts):
                steps.append(RenderStep("break_hint", DISPLAY_BREAK_HINT, tags + ("display_break_hint",)))

    for block_index, block in enumerate(document.blocks):
        block_tag = "paragraph"
        prefix = ""
        if block.kind == "heading":
            block_tag = f"heading_{min(max(block.level, 1), 3)}"
        elif block.kind == "unordered_item":
            block_tag, prefix = "list", "• "
        elif block.kind == "ordered_item":
            block_tag, prefix = "list", f"{block.ordinal or 1}. "
        elif block.kind == "spacer":
            block_tag = "retrieval_spacer"

        indent_tag = f"list_indent_{block_index}" if prefix else ""
        base_tags = (block_tag,) + ((indent_tag,) if indent_tag else ())
        if prefix:
            indent_prefixes.append((indent_tag, prefix))
            emit("indent", prefix, base_tags)
            record(prefix, block.canonical_prefix or prefix)

        previous_last_char = ""
        canonical_prefix = "" if prefix else block.canonical_prefix
        for span_index, span in enumerate(block.spans):
            tags = base_tags + (() if span.style == "plain" else (span.style,))
            if previous_last_char and span.text and display_break_opportunity(previous_last_char, span.text[0]):
                steps.append(RenderStep("break_hint", DISPLAY_BREAK_HINT, tags + ("display_break_hint",)))
            emit("text", span.text, tags)
            canonical = span.canonical_text if span.canonical_text is not None else span.text
            if span_index == 0:
                canonical = f"{canonical_prefix}{canonical}"
            record(span.text, canonical)
            if span.text:
                previous_last_char = span.text[-1]
        steps.append(RenderStep("newline", "\n", base_tags))
        record("\n", "\n")

    return PopupRenderPlan(tuple(steps), tuple(segments), tuple(indent_prefixes))


def project_selection_text(
    segments: tuple[RenderSelectionSegment, ...],
    selection_start: int,
    selection_end: int,
) -> str:
    projected: list[str] = []
    for segment in segments:
        start = max(selection_start, segment.offset)
        end = min(selection_end, segment.end)
        if start >= end:
            continue
        if start == segment.offset and end == segment.end:
            projected.append(segment.canonical_text)
        else:
            projected.append(
                segment.display_text[start - segment.offset : end - segment.offset]
            )
    return "".join(projected)
