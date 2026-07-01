from __future__ import annotations

from ClipAI.app.config import load_action_catalog


def test_action_config_loads_english_companion() -> None:
    catalog = load_action_catalog("config/actions.yaml")

    action = catalog.get("english_companion")

    assert action.id == "english_companion"
    assert action.name == "English Companion"
    assert action.hotkey == "ctrl+alt+8"


def test_long_press_uses_press_variant_prompt() -> None:
    catalog = load_action_catalog("config/actions.yaml")

    resolved = catalog.resolve("english_companion", "long")

    assert resolved.name == "英文改善建議"
    assert "Improve the following English" in resolved.prompt
    assert "English improvement coach" in resolved.system_prompt
