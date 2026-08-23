from __future__ import annotations

import pytest

from ClipAI.core.models import ResolvedAction, WorkflowStep
from ClipAI.services.follow_up_continuation import FollowUpContinuation
from ClipAI.services.prompt_builder import PromptBuilder


def _action() -> ResolvedAction:
    return ResolvedAction(
        id="explain",
        name="Explain",
        system_prompt="Action policy",
        prompt="Explain: {input}",
        press_type="short",
        input_mode="selection_or_clipboard",
        output_mode="popup",
        temperature=0.4,
    )


def _step(index: int) -> WorkflowStep:
    return WorkflowStep(
        step_id=f"step-{index}",
        action_id="explain",
        title="Explain",
        input_text="root input" if index == 0 else f"question-{index}",
        result_text=f"answer-{index}",
        output_profile="plain_text",
    )


@pytest.mark.parametrize(
    ("root_kind", "expected_action_id", "expected_source", "expected_context"),
    (
        (
            "action",
            "explain",
            "workflow_result",
            (
                "Explain: root input",
                "answer-0",
                "question-2",
                "answer-2",
                "question-3",
                "answer-3",
                "question-4",
                "answer-4",
                "next question",
            ),
        ),
        (
            "voice_draft",
            "voice_draft_follow_up",
            "voice_draft",
            (
                "Reviewed voice draft:\ncanonical draft",
                "question-2",
                "answer-2",
                "question-3",
                "answer-3",
                "question-4",
                "answer-4",
                "next question",
            ),
        ),
        (
            "contextual_question",
            "contextual_question",
            "selection",
            (
                "<source_context>\nfixed source\n</source_context>",
                "question-2",
                "answer-2",
                "question-3",
                "answer-3",
                "question-4",
                "answer-4",
                "next question",
            ),
        ),
    ),
)
def test_follow_up_roots_share_one_bounded_continuation_interface(
    root_kind: str,
    expected_action_id: str,
    expected_source: str,
    expected_context: tuple[str, ...],
) -> None:
    history = tuple(_step(index) for index in range(5))
    if root_kind == "action":
        continuation = FollowUpContinuation.for_action(_action(), "next question", history=history)
    elif root_kind == "voice_draft":
        continuation = FollowUpContinuation.for_voice_draft(
            "next question",
            "canonical draft",
            history=history,
        )
    else:
        continuation = FollowUpContinuation.for_contextual_question(
            "next question",
            "fixed source",
            "selection",
            history=history,
        )

    document = continuation.input_document("workflow-1")
    request = PromptBuilder("App policy").build_follow_up(
        continuation,
        model="captured-model",
        default_temperature=0.2,
    )

    assert continuation.action.id == expected_action_id
    assert continuation.parent_step_id == "step-4"
    assert document.source == expected_source
    assert document.workflow_id == "workflow-1"
    assert document.step_id == "step-4"
    assert tuple(message.content for message in request.messages[1:]) == expected_context
    assert request.model == "captured-model"
    assert request.temperature == (0.4 if root_kind == "action" else 0.2)


def test_initial_contextual_question_keeps_source_separate_from_question() -> None:
    continuation = FollowUpContinuation.for_contextual_question(
        "What does this imply?",
        "The source is fixed.",
        "clipboard",
    )

    request = PromptBuilder("App policy").build_follow_up(
        continuation,
        model="captured-model",
        default_temperature=0.2,
    )

    assert continuation.parent_step_id is None
    assert continuation.input_document("workflow-1").text == "What does this imply?"
    assert [message.content for message in request.messages[1:]] == [
        "<source_context>\nThe source is fixed.\n</source_context>",
        "What does this imply?",
    ]


def test_action_continuation_requires_a_completed_root_step() -> None:
    with pytest.raises(ValueError, match="completed Workflow step"):
        FollowUpContinuation.for_action(_action(), "question", history=())
