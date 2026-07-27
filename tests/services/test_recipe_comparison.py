from __future__ import annotations

import pytest

from ClipAI.core.models import ActionFeedbackRecord
from ClipAI.services.recipe_comparison import RecipeComparisonPolicy


def record(
    feedback_id: str,
    *,
    outcome: str,
    created_at: str,
    saved: bool = True,
) -> ActionFeedbackRecord:
    return ActionFeedbackRecord(
        record_schema_version=1,
        feedback_id=feedback_id,
        created_at=created_at,
        workflow_id=f"workflow-{feedback_id}",
        step_id=f"step-{feedback_id}",
        action_id="rewrite",
        action_version="v1",
        press_type="short",
        provider="openai",
        model="old-model",
        input_source="selection",
        outcome=outcome,
        input_text=f"input-{feedback_id}" if saved else None,
        result_text=f"result-{feedback_id}" if saved else None,
    )


def test_default_tests_choose_two_latest_negative_and_one_latest_helpful() -> None:
    records = (
        record("old-negative", outcome="needs_adjustment", created_at="2026-07-01"),
        record("new-helpful", outcome="helpful", created_at="2026-07-04"),
        record("newest-negative", outcome="needs_adjustment", created_at="2026-07-05"),
        record("middle-negative", outcome="needs_adjustment", created_at="2026-07-03"),
        record("not-saved", outcome="needs_adjustment", created_at="2026-07-06", saved=False),
    )

    selected = RecipeComparisonPolicy().default_feedback_ids(records)

    assert selected == ("newest-negative", "middle-negative", "new-helpful")


def test_without_helpful_case_default_uses_three_latest_negatives() -> None:
    records = tuple(
        record(str(index), outcome="needs_adjustment", created_at=f"2026-07-0{index}")
        for index in range(1, 5)
    )

    assert RecipeComparisonPolicy().default_feedback_ids(records) == ("4", "3", "2")


@pytest.mark.parametrize("count", [0, 6])
def test_user_must_choose_between_one_and_five_tests(count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        RecipeComparisonPolicy().validate_test_count(count)


@pytest.mark.parametrize(
    ("verdicts", "mode"),
    [
        (("candidate_better",), "direct"),
        (("candidate_better", "current_better"), "confirm"),
        (("current_better",), "blocked"),
        (("candidate_better", "both_need_work"), "blocked"),
        ((), "blocked"),
    ],
)
def test_apply_gate_reflects_successful_human_comparisons(verdicts, mode) -> None:
    assert RecipeComparisonPolicy().apply_gate(verdicts).mode == mode
