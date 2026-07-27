from __future__ import annotations

import ast
import inspect
import textwrap

from ClipAI.core.models import RecipeEvidenceItem
from ClipAI.ui.recipe_improvement import (
    RecipeImprovementDialog,
    default_test_ids,
)


def item(
    feedback_id: str,
    outcome: str,
    *,
    saved: bool = True,
) -> RecipeEvidenceItem:
    return RecipeEvidenceItem(
        feedback_id,
        f"2026-07-{feedback_id}",
        outcome,
        "",
        "",
        "openai",
        "gpt-test",
        saved,
        "input" if saved else None,
        "result" if saved else None,
    )


def test_default_test_controls_use_two_recent_negatives_and_helpful_guard() -> None:
    evidence = (
        item("05", "needs_adjustment"),
        item("04", "helpful"),
        item("03", "needs_adjustment"),
        item("02", "needs_adjustment"),
        item("01", "needs_adjustment", saved=False),
    )

    assert default_test_ids(evidence) == ("05", "03", "04")


def test_evidence_checkboxes_use_only_supported_customtkinter_arguments() -> None:
    source = textwrap.dedent(
        inspect.getsource(RecipeImprovementDialog._render_evidence)
    )
    tree = ast.parse(source)
    checkbox_calls = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "CTkCheckBox"
    )

    assert checkbox_calls
    assert all(
        keyword.arg != "wraplength"
        for call in checkbox_calls
        for keyword in call.keywords
    )
