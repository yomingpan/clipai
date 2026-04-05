from __future__ import annotations

from pathlib import Path

from clipai.actions import load_actions, resolve_action_variant


def test_rewrite_complete_no_longer_overrides_legacy_ollama_model() -> None:
    content = Path("config/actions.yaml").read_text(encoding="utf-8")
    assert "id: rewrite_complete" in content
    assert "model: gemma3:1b" not in content


def test_english_companion_action_loads_with_long_press_variant() -> None:
    actions = load_actions("config/config.yaml")
    action_map = {action["id"]: action for action in actions}

    assert "english_companion" in action_map
    action = action_map["english_companion"]
    assert action["hotkey"] == "ctrl+alt+8"
    assert action["output_mode"] == "popup"

    short_action = resolve_action_variant(action, "short")
    long_action = resolve_action_variant(action, "long")

    assert short_action.action_name == "English Companion"
    assert short_action.action_def["output_mode"] == "popup"
    assert "## Summary" in short_action.action_def["prompt"]
    assert "## More Natural Alternatives" in short_action.action_def["prompt"]

    assert long_action.action_name == "英文改善建議"
    assert long_action.action_def["output_mode"] == "popup"
    assert "## What Sounds Off" in long_action.action_def["prompt"]
    assert "## Full Rewrite" in long_action.action_def["prompt"]
