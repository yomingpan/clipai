from __future__ import annotations

from dataclasses import dataclass

import pytest

from clipai.core.cancellation import CancellationController
from clipai.core.constants import EVENT_ACTION_COMPLETE, EVENT_ACTION_ERROR, EVENT_ACTION_START, EVENT_PIPELINE_UPDATE
from clipai.core.event_bus import EventBus
from clipai.core.llm_provider import ProviderChunk
from clipai.services.action_service import ActionService
from clipai.services.resolve_config import ResolvedActionConfig


class _ProviderOK:
    def chat_completion(self, **kwargs):
        del kwargs
        yield ProviderChunk(content="A")
        yield ProviderChunk(content="B")


class _ProviderErr:
    def chat_completion(self, **kwargs):
        del kwargs
        raise RuntimeError("boom")
        yield


def _config() -> ResolvedActionConfig:
    return ResolvedActionConfig(
        action_id="a1",
        action_name="summarize",
        mode="balanced",
        provider="gemini",
        model="m",
        stream=True,
        temperature=0.2,
        output={"popup": True},
        template="{input}",
    )


def test_action_service_event_sequence_success() -> None:
    bus = EventBus()
    service = ActionService(bus, _ProviderOK())

    seen: list[str] = []
    bus.subscribe(EVENT_ACTION_START, lambda _: seen.append(EVENT_ACTION_START))
    bus.subscribe(EVENT_PIPELINE_UPDATE, lambda _: seen.append(EVENT_PIPELINE_UPDATE))
    bus.subscribe(EVENT_ACTION_COMPLETE, lambda _: seen.append(EVENT_ACTION_COMPLETE))

    ctrl = CancellationController()
    result = service.run_action(_config(), [{"role": "user", "content": "x"}], None, ctrl.token)

    assert result.content == "AB"
    assert seen[0] == EVENT_ACTION_START
    assert seen[-1] == EVENT_ACTION_COMPLETE
    assert seen.count(EVENT_PIPELINE_UPDATE) == 2


def test_action_service_error_publishes_action_error() -> None:
    bus = EventBus()
    service = ActionService(bus, _ProviderErr())
    seen: list[dict] = []
    bus.subscribe(EVENT_ACTION_ERROR, lambda payload: seen.append(payload))

    with pytest.raises(RuntimeError):
        service.run_action(_config(), [{"role": "user", "content": "x"}], None, None)

    assert len(seen) == 1
    assert seen[0]["action_id"] == "a1"
