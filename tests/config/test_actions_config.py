from __future__ import annotations

from pathlib import Path

from clipai.actions import load_actions, resolve_action_variant


SUMMARY_NAME = "\u7e3d\u7d50\u91cd\u9ede\u8207\u4e0b\u4e00\u6b65"
SUMMARY_LONG_NAME = "\u89e3\u91cb\u5167\u5bb9"


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
    assert "## Context" in short_action.action_def["prompt"]
    assert "## Words & Phrases" in short_action.action_def["prompt"]
    assert "## Natural Examples" in short_action.action_def["prompt"]

    assert long_action.action_def["output_mode"] == "popup"
    assert "## What Sounds Off" in long_action.action_def["prompt"]
    assert "## Better Ways To Say It" in long_action.action_def["prompt"]
    assert "## Full Rewrite" in long_action.action_def["prompt"]


def test_popup_summary_action_uses_compact_popup_structure() -> None:
    actions = load_actions("config/config.yaml")
    action_map = {action["id"]: action for action in actions}

    action = action_map["summarize_next_steps"]
    short_action = resolve_action_variant(action, "short")
    long_action = resolve_action_variant(action, "long")

    assert short_action.action_name == SUMMARY_NAME
    assert "MECE" in short_action.action_def["system_prompt"]
    assert "1-2" in short_action.action_def["system_prompt"]
    assert "## \u91cd\u9ede" in short_action.action_def["prompt"]
    assert "## \u5206\u985e\u8981\u9ede" in short_action.action_def["prompt"]
    assert "## \u4e0b\u4e00\u6b65" in short_action.action_def["prompt"]
    assert "## \u95dc\u9375\u539f\u6587" in short_action.action_def["prompt"]
    assert "1 \u9ede" in short_action.action_def["prompt"]

    assert long_action.action_name == SUMMARY_LONG_NAME
    assert "\u6838\u5fc3\u610f\u601d" in long_action.action_def["system_prompt"]
    assert "\u95dc\u9375\u6982\u5ff5" in long_action.action_def["system_prompt"]


def test_config_files_are_readable_utf8_without_mojibake_markers() -> None:
    config_content = Path("config/config.yaml").read_text(encoding="utf-8")
    actions_content = Path("config/actions.yaml").read_text(encoding="utf-8")

    assert "ClipAI" in config_content
    assert SUMMARY_NAME in actions_content
    assert "\ufffd" not in config_content
    assert "\ufffd" not in actions_content
