from ClipAI.core.models import InlineSpan, PresentationBlock, PresentationDocument
from ClipAI.ui.presentation_render import build_popup_render_plan, project_selection_text


def test_rendered_content_owns_canonical_fragments_and_widget_block_ranges():
    from dataclasses import FrozenInstanceError
    import pytest
    from ClipAI.ui.presentation_render import RenderedContent
    document = PresentationDocument((
        PresentationBlock('heading', (InlineSpan('Title'),), canonical_prefix='# '),
        PresentationBlock('unordered_item', (InlineSpan('item', 'bold', '**item**'),), canonical_prefix='- '),
    ), '# Title\n- **item**')
    content = RenderedContent.from_plan(document, build_popup_render_plan(document))
    assert content.canonical_text == '# Title\n- **item**\n'
    assert content.project_selection(0, 5) == '# Title'
    assert len(content.block_ranges) == 2
    with pytest.raises(FrozenInstanceError):
        content.canonical_text = 'changed'


def test_rendered_content_fallback_chunks_edit_and_append_are_canonical():
    from ClipAI.ui.presentation_render import RenderedContent
    fallback = RenderedContent.from_plan(PresentationDocument((), 'fallback\n'), None)
    assert fallback.canonical_text == 'fallback\n'
    assert fallback.selection_segments == fallback.block_ranges == ()
    chunks = RenderedContent.from_chunks([('first', 'heading'), ('\nsecond', 'body')])
    assert chunks.canonical_text == 'first\nsecond'
    assert RenderedContent.editable('original\n').canonical_text == 'original\n'
    document = PresentationDocument((PresentationBlock('paragraph', (InlineSpan('bold', 'bold', '**bold**'),)),), '**bold**')
    rendered = RenderedContent.from_plan(document, build_popup_render_plan(document))
    appended = rendered.appended('next')
    assert appended.canonical_text == '**bold**\nnext'
    assert appended.selection_segments == appended.block_ranges == ()
    assert rendered.canonical_text == '**bold**\n'


def test_render_plan_projects_structure_without_a_widget() -> None:
    document = PresentationDocument(
        (
            PresentationBlock("heading", (InlineSpan("Title"),), level=2, canonical_prefix="## "),
            PresentationBlock("unordered_item", (InlineSpan("First", "bold", "**First**"),), canonical_prefix="- "),
            PresentationBlock("ordered_item", (InlineSpan("Second"),), ordinal=2, canonical_prefix="2. "),
            PresentationBlock("spacer", (InlineSpan("\n\n", canonical_text=""),)),
        ),
        "fallback",
    )

    plan = build_popup_render_plan(document)

    assert "indent" in [step.kind for step in plan.steps]
    assert "newline" in [step.kind for step in plan.steps]
    assert plan.indent_prefixes == (("list_indent_1", "• "), ("list_indent_2", "2. "))
    assert project_selection_text(plan.selection_segments, 0, 5) == "## Title"
    assert project_selection_text(plan.selection_segments, 8, 13) == "**First**"


def test_partial_or_cross_segment_selection_uses_visible_text() -> None:
    document = PresentationDocument(
        (PresentationBlock("paragraph", (InlineSpan("bold", "bold", "**bold**"), InlineSpan(" tail"))),),
        "**bold** tail",
    )
    plan = build_popup_render_plan(document)

    assert project_selection_text(plan.selection_segments, 0, 4) == "**bold**"
    assert project_selection_text(plan.selection_segments, 1, 6) == "old t"
