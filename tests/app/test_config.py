from __future__ import annotations

from ClipAI.app.config import load_action_catalog, load_app_config


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


def test_app_config_loads_provider_settings() -> None:
    config = load_app_config("config/config.yaml")

    assert config.provider_name == "gemini"
    assert config.provider_config["provider"] == "gemini"
    assert config.provider_config["gemini_base_url"] == "https://generativelanguage.googleapis.com"
    assert config.default_model == "gemma-4-31b-it"
