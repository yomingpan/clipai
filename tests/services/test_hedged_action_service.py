from __future__ import annotations

import time

import pytest

from clipai.core.event_bus import EventBus
from clipai.core.llm_provider import ProviderChunk
from clipai.services.action_config import ResolvedActionConfig
from clipai.services.hedged_action_service import HedgeRoute, HedgedActionService


class _TimedProvider:
    def __init__(self, chunks: list[str], *, delay: float = 0.0, fail: Exception | None = None) -> None:
        self._chunks = chunks
        self._delay = delay
        self._fail = fail

    def chat_completion(self, *, cancellation_token=None, **kwargs):
        del kwargs
        if self._fail is not None:
            raise self._fail
        for item in self._chunks:
            time.sleep(self._delay)
            if cancellation_token and cancellation_token.is_cancelled():
                return
            yield ProviderChunk(content=item)


def _config() -> ResolvedActionConfig:
    return ResolvedActionConfig(
        action_id="a1",
        action_name="popup",
        mode="desktop_hotkey",
        provider="gemini",
        model="primary-model",
        stream=True,
        temperature=0.2,
        output={"popup": True},
        template="{input}",
    )


def test_fallback_wins_when_primary_is_slower() -> None:
    service = HedgedActionService(EventBus())
    seen: list[str] = []

    result = service.run_action(
        _config(),
        [{"role": "user", "content": "hello"}],
        HedgeRoute("primary", _TimedProvider(["slow"], delay=0.05), "p-model", "gemini"),
        HedgeRoute("fallback", _TimedProvider(["fast"], delay=0.0), "f-model", "ollama"),
        temperature=0.2,
        stream=True,
        on_chunk=lambda chunk: seen.append(chunk),
        hedge_delay_ms=1,
    )

    assert result.content == "fast"
    assert seen == ["fast"]


def test_primary_failure_falls_back_to_secondary() -> None:
    service = HedgedActionService(EventBus())

    result = service.run_action(
        _config(),
        [{"role": "user", "content": "hello"}],
        HedgeRoute("primary", _TimedProvider([], fail=RuntimeError("boom")), "p-model", "gemini"),
        HedgeRoute("fallback", _TimedProvider(["ok"], delay=0.0), "f-model", "ollama"),
        temperature=0.2,
        stream=True,
        hedge_delay_ms=1,
    )

    assert result.content == "ok"


def test_both_fail_raise_error() -> None:
    service = HedgedActionService(EventBus())

    with pytest.raises(RuntimeError):
        service.run_action(
            _config(),
            [{"role": "user", "content": "hello"}],
            HedgeRoute("primary", _TimedProvider([], fail=RuntimeError("pboom")), "p-model", "gemini"),
            HedgeRoute("fallback", _TimedProvider([], fail=RuntimeError("fboom")), "f-model", "ollama"),
            temperature=0.2,
            stream=True,
            hedge_delay_ms=1,
        )
