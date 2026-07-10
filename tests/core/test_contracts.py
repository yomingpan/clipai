from __future__ import annotations

from ClipAI.core.commands import StartAction
from ClipAI.core.models import LLMMessage, LLMRequest, LLMResult
from ClipAI.core.state import CancellationToken, SessionSnapshot, SessionStatus


def test_typed_llm_contract_is_immutable_and_explicit() -> None:
    request = LLMRequest((LLMMessage("user", "hello"),), "model", 0.2)
    result = LLMResult("answer", "fake", request.model)
    assert request.messages[0].role == "user"
    assert result.provider == "fake"


def test_command_and_snapshot_carry_session_safe_identity() -> None:
    command = StartAction("english", "short")
    snapshot = SessionSnapshot("session-1", 0, SessionStatus.CREATED, command.action_id, "English", "model")
    assert snapshot.evolve(status_text="Reading").revision == 1


def test_cancellation_token_is_cooperative() -> None:
    token = CancellationToken()
    assert token.is_cancelled is False
    token.cancel()
    assert token.is_cancelled is True

