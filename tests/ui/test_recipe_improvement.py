from __future__ import annotations

from ClipAI.core.models import RecipeEvidenceItem
from ClipAI.ui.recipe_improvement import default_test_ids


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
