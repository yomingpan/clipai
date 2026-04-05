from __future__ import annotations

from clipai.actions import resolve_action_variant
from clipai.app.config import AppConfigBundle
from clipai.context.input_resolver import InputResolution
from clipai.context.runtime_context import build_runtime_context
from clipai.core.event_bus import EventBus
from clipai.services.action_runner import ActionRunner, RunRequest
from clipai.services.action_service import ActionRunResult


def _bundle(actions: list[dict]) -> AppConfigBundle:
    return AppConfigBundle(
        config_path="config/config.yaml",
        cfg={},
        app_cfg={"system_prompt": "Global system", "temperature": 0.2},
        provider_cfg={"provider": "gemini", "default_model": "gemini-1.5-flash"},
        tts_cfg={},
        actions=actions,
        action_map={action["id"]: action for action in actions},
    )


def test_run_resolved_action_uses_long_variant_prompt_and_output_mode(monkeypatch) -> None:
    bundle = _bundle(
        [
            {
                "id": "summarize",
                "name": "Summary",
                "prompt": "Base prompt: {input}",
                "system_prompt": "Base system",
                "input_mode": "selection_or_clipboard",
                "output_mode": "paste",
                "press_variants": {
                    "long": {
                        "name": "Explain",
                        "prompt": "Explain prompt: {input}",
                        "system_prompt": "Explain system",
                        "output_mode": "popup",
                        "temperature": 0.7,
                    }
                },
            }
        ]
    )
    runner = ActionRunner(bundle, event_bus=EventBus())
    captured: dict[str, object] = {}

    monkeypatch.setattr("clipai.services.action_runner.build_provider", lambda cfg: {"provider": cfg["provider"]})

    class _FakeActionService:
        def __init__(self, event_bus, provider) -> None:
            del event_bus
            captured["provider"] = provider

        def run_action(self, config, messages, cancellation_token, source_meta=None, on_chunk=None):
            del cancellation_token, source_meta, on_chunk
            captured["config"] = config
            captured["messages"] = messages
            return ActionRunResult(action_id=config.action_id, content="done")

    class _FakeResolver:
        def __init__(self, enable_selection_capture: bool) -> None:
            captured["enable_selection_capture"] = enable_selection_capture

        def resolve_text(self, explicit_text, input_mode: str = "selection_or_clipboard") -> InputResolution:
            captured["explicit_text"] = explicit_text
            captured["input_mode"] = input_mode
            return InputResolution(text="selected text", source="selection")

    monkeypatch.setattr("clipai.services.action_runner.ActionService", _FakeActionService)
    monkeypatch.setattr("clipai.services.action_runner.InputResolver", _FakeResolver)

    outcome = runner.run_resolved_action(
        resolve_action_variant(bundle.action_map["summarize"], "long"),
        build_runtime_context(
            mode="desktop_hotkey",
            apply_output=False,
            use_selection=True,
            stream_enabled=True,
            stream_to_stdout=False,
        ),
    )

    assert outcome.action_name == "Explain"
    assert outcome.press_type == "long"
    assert outcome.output_mode == "popup"
    assert captured["input_mode"] == "selection_or_clipboard"
    assert captured["enable_selection_capture"] is True
    assert captured["messages"] == [
        {"role": "system", "content": "Global system\n\nExplain system"},
        {"role": "user", "content": "Explain prompt: selected text"},
    ]
    assert captured["config"].temperature == 0.7


def test_run_request_defaults_to_short_variant_for_legacy_actions(monkeypatch) -> None:
    bundle = _bundle(
        [
            {
                "id": "summarize",
                "name": "Summary",
                "prompt": "Base prompt: {input}",
                "system_prompt": "Base system",
                "input_mode": "selection_or_clipboard",
                "output_mode": "paste",
                "press_variants": {
                    "long": {
                        "prompt": "Explain prompt: {input}",
                    }
                },
            }
        ]
    )
    runner = ActionRunner(bundle, event_bus=EventBus())
    captured: dict[str, object] = {}

    monkeypatch.setattr("clipai.services.action_runner.build_provider", lambda cfg: {"provider": cfg["provider"]})

    class _FakeActionService:
        def __init__(self, event_bus, provider) -> None:
            del event_bus, provider

        def run_action(self, config, messages, cancellation_token, source_meta=None, on_chunk=None):
            del cancellation_token, source_meta, on_chunk
            captured["config"] = config
            captured["messages"] = messages
            return ActionRunResult(action_id=config.action_id, content="done")

    class _FakeResolver:
        def __init__(self, enable_selection_capture: bool) -> None:
            del enable_selection_capture

        def resolve_text(self, explicit_text, input_mode: str = "selection_or_clipboard") -> InputResolution:
            del explicit_text, input_mode
            return InputResolution(text="selected text", source="selection")

    monkeypatch.setattr("clipai.services.action_runner.ActionService", _FakeActionService)
    monkeypatch.setattr("clipai.services.action_runner.InputResolver", _FakeResolver)

    outcome = runner.run(
        RunRequest(action_id="summarize"),
        build_runtime_context(
            mode="desktop_hotkey",
            apply_output=False,
            use_selection=True,
            stream_enabled=True,
            stream_to_stdout=False,
        ),
    )

    assert outcome.press_type == "short"
    assert outcome.output_mode == "paste"
    assert captured["messages"][1]["content"] == "Base prompt: selected text"
