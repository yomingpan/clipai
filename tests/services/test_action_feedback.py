from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from ClipAI.core.commands import SubmitActionFeedback
from ClipAI.core.models import ActionFeedbackContract, FeedbackReason, WorkflowStep
from ClipAI.platform.action_feedback import JsonlActionFeedbackStore
from ClipAI.services.action_feedback import ActionFeedbackService


class MemoryStore:
    def __init__(self) -> None:
        self.records = []

    def append(self, record) -> None:
        self.records.append(record)


def make_step() -> WorkflowStep:
    return WorkflowStep(
        step_id="step-1",
        action_id="shorten_content",
        title="Shorten Content",
        input_text="original private text",
        result_text="short result",
        output_profile="plain_text",
        input_source="selection",
        feedback_contract=ActionFeedbackContract(
            "Shorten faithfully",
            "Keep meaning",
            "Does it still represent you?",
            (FeedbackReason("meaning_lost", "Core meaning was lost"), FeedbackReason("other", "Other")),
        ),
        action_version="abc123",
        provider="fake",
        model="fake-model",
    )


def test_feedback_does_not_preserve_content_by_default() -> None:
    store = MemoryStore()
    service = ActionFeedbackService(store, lambda: datetime(2026, 7, 19, tzinfo=timezone.utc))

    record = service.record("workflow-1", make_step(), SubmitActionFeedback(
        "workflow-1", "step-1", "feedback-1", "helpful"
    ))

    assert record.input_text is None
    assert record.result_text is None
    assert record.action_version == "abc123"
    assert record.created_at == "2026-07-19T00:00:00+00:00"


def test_explicit_adjustment_case_preserves_input_and_output_and_execution_metadata() -> None:
    store = MemoryStore()
    service = ActionFeedbackService(store)

    record = service.record("workflow-1", make_step(), SubmitActionFeedback(
        "workflow-1",
        "step-1",
        "feedback-1",
        "needs_adjustment",
        reason="meaning_lost",
        note="  lost the caveat  ",
        save_case=True,
    ))

    assert record.input_text == "original private text"
    assert record.result_text == "short result"
    assert record.note == "lost the caveat"
    assert record.record_schema_version == 1
    assert record.press_type == "short"
    assert record.provider == "fake"
    assert record.model == "fake-model"


def test_explicit_helpful_case_preserves_input_and_output() -> None:
    service = ActionFeedbackService(MemoryStore())

    record = service.record("workflow-1", make_step(), SubmitActionFeedback(
        "workflow-1", "step-1", "feedback-1", "helpful", save_case=True
    ))

    assert record.input_text == "original private text"
    assert record.result_text == "short result"


def test_invalid_reason_is_rejected() -> None:
    service = ActionFeedbackService(MemoryStore())

    with pytest.raises(ValueError, match="valid feedback reason"):
        service.record("workflow-1", make_step(), SubmitActionFeedback(
            "workflow-1", "step-1", "feedback-1", "needs_adjustment", reason="unknown"
        ))


def test_feedback_target_must_match_completed_step() -> None:
    service = ActionFeedbackService(MemoryStore())

    with pytest.raises(ValueError, match="does not match"):
        service.record("workflow-1", make_step(), SubmitActionFeedback(
            "workflow-1", "other-step", "feedback-1", "helpful"
        ))


def test_jsonl_store_serializes_one_append_only_record(tmp_path) -> None:
    path = tmp_path / "feedback.jsonl"
    service = ActionFeedbackService(JsonlActionFeedbackStore(path))

    service.record("workflow-1", make_step(), SubmitActionFeedback(
        "workflow-1", "step-1", "feedback-1", "not_applicable"
    ))

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["record_schema_version"] == 1
    assert payload["feedback_id"] == "feedback-1"
    assert payload["outcome"] == "not_applicable"
    assert payload["press_type"] == "short"
    assert payload["provider"] == "fake"
    assert payload["model"] == "fake-model"
    assert payload["input_text"] is None
