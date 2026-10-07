from ClipAI.core.models import InlineSpan, PresentationBlock, PresentationDocument
from ClipAI.ui.presentation_render import build_popup_render_plan, project_selection_text


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
