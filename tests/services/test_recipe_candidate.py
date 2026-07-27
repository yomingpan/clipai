from __future__ import annotations

import json

import pytest

from ClipAI.core.models import (
    ActionFeedbackRecord,
    LLMResult,
    ResolvedAction,
)
from ClipAI.services.recipe_candidate import RecipeCandidateService


def action() -> ResolvedAction:
    return ResolvedAction(
        id="rewrite",
        name="Rewrite",
        system_prompt="Be concise.",
        prompt="Rewrite:\n\n{input}",
        press_type="short",
        input_mode="selection_or_clipboard",
        output_mode="popup",
        temperature=0.2,
        version_id="parent-v1",
    )


def evidence() -> ActionFeedbackRecord:
    return ActionFeedbackRecord(
        record_schema_version=1,
        feedback_id="feedback-1",
        created_at="2026-07-27T00:00:00+00:00",
        workflow_id="workflow-1",
        step_id="step-1",
        action_id="rewrite",
        action_version="parent-v1",
        press_type="short",
        provider="openai",
        model="gpt-old",
        input_source="selection",
        outcome="needs_adjustment",
        reason="too_long",
        note="Keep the conclusion.",
        input_text="Original text",
        result_text="Old result",
    )


def test_generation_request_contains_only_selected_evidence_and_fixed_candidate_scope() -> None:
    request = RecipeCandidateService().build_request(
        action(),
        (evidence(),),
        directions=("更清楚", "保留細節"),
        user_direction="不要刪掉結論",
        model="gpt-current",
    )

    assert request.model == "gpt-current"
    payload = json.loads(request.messages[1].content)
    assert payload["recipe"]["system_prompt"] == "Be concise."
    assert payload["recipe"]["prompt"] == "Rewrite:\n\n{input}"
    assert payload["selected_evidence"][0]["input"] == "Original text"
    assert payload["selected_evidence"][0]["result"] == "Old result"
    assert payload["allowed_changes"] == ["system_prompt", "prompt"]
    assert "name" not in payload["allowed_changes"]


def test_valid_candidate_is_tied_to_parent_version_and_iteration() -> None:
    result = LLMResult(
        text=json.dumps(
            {
                "classification": "prompt",
                "explanation_zh_tw": "讓限制更明確。",
                "problem_summary_zh_tw": "結論容易遺失。",
                "proposed_change_zh_tw": "加入保留結論的限制。",
                "preserve_behavior_zh_tw": "仍需保持精簡。",
                "system_prompt": "Be concise and preserve conclusions.",
                "prompt": "Rewrite while preserving the conclusion:\n\n{input}",
            }
        ),
        provider="openai",
        model="gpt-current",
    )

    candidate = RecipeCandidateService().parse_candidate(
        action(), result, iteration=2
    )

    assert candidate.parent_version == "parent-v1"
    assert candidate.iteration == 2
    assert candidate.provider == "openai"
    assert candidate.model == "gpt-current"
    assert candidate.explanation == "讓限制更明確。"
    assert candidate.problem_summary == "結論容易遺失。"
    assert candidate.proposed_change == "加入保留結論的限制。"
    assert candidate.preserve_behavior == "仍需保持精簡。"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "classification": "prompt",
                "explanation_zh_tw": "x",
                "proposed_change_zh_tw": "x",
                "preserve_behavior_zh_tw": "x",
                "system_prompt": "new",
                "prompt": "{input}",
            },
            "problem_summary_zh_tw is required",
        ),
        (
            {
                "classification": "prompt",
                "explanation_zh_tw": "x",
                "problem_summary_zh_tw": "x",
                "proposed_change_zh_tw": "x",
                "preserve_behavior_zh_tw": "x",
                "system_prompt": "new",
                "prompt": "{input} {input}",
            },
            "exactly once",
        ),
        (
            {
                "classification": "prompt",
                "explanation_zh_tw": "x",
                "problem_summary_zh_tw": "x",
                "proposed_change_zh_tw": "x",
                "preserve_behavior_zh_tw": "x",
                "system_prompt": "new",
                "prompt": "{document}",
            },
            "supported template variable",
        ),
        (
            {
                "classification": "prompt",
                "explanation_zh_tw": "x",
                "problem_summary_zh_tw": "x",
                "proposed_change_zh_tw": "x",
                "preserve_behavior_zh_tw": "x",
                "system_prompt": "new",
                "prompt": "{input}",
                "temperature": 0.9,
            },
            "unexpected candidate fields",
        ),
    ],
)
def test_invalid_or_out_of_scope_candidate_is_rejected(payload, message) -> None:
    with pytest.raises(ValueError, match=message):
        RecipeCandidateService().parse_candidate(
            action(),
            LLMResult(json.dumps(payload), "openai", "gpt-current"),
            iteration=1,
        )


def test_suspected_app_issue_returns_classification_without_candidate() -> None:
    proposal = RecipeCandidateService().parse_proposal(
        action(),
        LLMResult(
            json.dumps(
                {
                    "classification": "app_issue",
                    "explanation_zh_tw": "輸出似乎在顯示階段被截斷。",
                }
            ),
            "openai",
            "gpt-current",
        ),
        iteration=1,
    )

    assert proposal.classification == "app_issue"
    assert proposal.candidate is None
    assert proposal.explanation == "輸出似乎在顯示階段被截斷。"
