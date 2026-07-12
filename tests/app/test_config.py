from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.app.config_loader import load_action_catalog, load_app_config, load_config_bundle, load_output_profiles, load_shortcut_catalog
from ClipAI.app.readiness import assess_provider_readiness
from ClipAI.core.errors import ConfigError
from ClipAI.providers.settings import ProviderCredential


def test_config_bundle_loads_typed_provider_and_action_settings() -> None:
    bundle = load_config_bundle()

    assert bundle.providers.active == "gemini"
    assert bundle.providers.gemini.model == "gemini-3.1-flash-lite"
    assert bundle.runtime.max_workers == 2
    assert bundle.app.modifier_mode == "ctrl_alt"
    action = bundle.actions.get("english_companion")
    assert action.input_mode == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is False
    assert action.temperature == 0.2
    assert action.output_profile == "english_learning_compact"
    assert bundle.output_profiles.get(action.output_profile).required_markers == ()
    assert bundle.output_profiles.get(action.output_profile).presentation == "plain_text"
    assert "appears literally in the input" in action.system_prompt
    assert "never substitute, infer, or invent" in action.system_prompt
    assert "記憶：" in action.prompt
    assert bundle.schema_versions.app == 1
    assert bundle.schema_versions.actions == 3
    assert bundle.schema_versions.output_profiles == 1
    assert bundle.schema_versions.shortcuts == 1
    assert bundle.shortcuts.resolve("english_companion", "long").action_id == "english_companion"


def test_v4_context_actions_have_expected_hotkeys_and_support_multimodal_input() -> None:
    bundle = load_config_bundle()
    expected = {
        "translate_to_traditional_chinese": "ctrl+alt+1",
        "translate_to_english": "ctrl+alt+2",
        "name_idea": "ctrl+alt+3",
        "illuminate_essence": "ctrl+alt+4",
        "pyramid_position": "ctrl+alt+5",
        "explain_like_friend": "ctrl+alt+6",
        "article_structure": "ctrl+alt+7",
        "english_companion": "ctrl+alt+8",
        "reflective_question": "ctrl+alt+9",
        "critical_thinking": "ctrl+alt+0",
        "extract_keywords": "ctrl+alt+e",
    }

    for shortcut_id, hotkey in expected.items():
        shortcut = bundle.shortcuts.definition(shortcut_id)
        assert shortcut.hotkey == hotkey
        assert shortcut.action_id == shortcut_id
        action = bundle.actions.get(shortcut.action_id)
        assert action.input_mode == "selection_or_clipboard"
        assert action.input_policy == "external_text"
        assert "image" in action.system_prompt.lower() or "圖片" in action.system_prompt


def test_long_press_uses_variant_prompt() -> None:
    resolved = load_action_catalog("config/actions.yaml").resolve("english_companion", "long")
    assert resolved.name == "英文改善建議"
    assert "Improve the following English" in resolved.prompt
    assert resolved.output_profile == "english_improvement"


def test_action_input_mode_defaults_to_selection_or_clipboard(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text(
        """schema_version: 3
actions:
  - id: default_input
    name: Default Input
    system_prompt: system
    prompt: "{input}"
  - id: clipboard_only
    name: Clipboard Only
    system_prompt: system
    prompt: "{input}"
    input_mode: clipboard
""",
        encoding="utf-8",
    )

    catalog = load_action_catalog(path)
    assert catalog.resolve("default_input", "short").input_mode == "selection_or_clipboard"
    assert catalog.resolve("clipboard_only", "short").input_mode == "clipboard"


def test_unknown_config_field_reports_full_path(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
app:
  temperature: 0.2
  typo_field: true
provider:
  active: fake
  gemini: {}
  openai: {}
  anthropic: {}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"config\.app\.typo_field"):
        load_app_config(path)


def test_invalid_runtime_worker_count_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
app: {}
provider:
  active: fake
  gemini: {}
  openai: {}
  anthropic: {}
runtime:
  max_workers: 0
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="max_workers"):
        load_app_config(path)


def test_invalid_logging_level_is_rejected_by_config_loader(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "app: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\nlogging:\n  level: verbose\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"config\.logging\.level"):
        load_app_config(path)


def test_missing_schema_version_is_accepted_as_legacy_without_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    original = "app: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\n"
    path.write_text(original, encoding="utf-8")
    load_app_config(path)
    assert path.read_text(encoding="utf-8") == original


def test_future_schema_version_reports_file_and_version(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"config\.yaml.*schema_version 2"):
        load_app_config(path)


@pytest.mark.parametrize(
    ("filename", "loader"),
    (("output_profiles.yaml", load_output_profiles),),
)
def test_future_catalog_schema_version_is_rejected(tmp_path: Path, filename: str, loader) -> None:
    path = tmp_path / filename
    path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"{filename}.*schema_version 2"):
        loader(path)


def test_future_actions_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text("schema_version: 4\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"actions.yaml.*schema_version 4"):
        load_action_catalog(path)


def test_action_input_policy_is_typed_and_shorten_is_contextual() -> None:
    catalog = load_action_catalog("config/actions.yaml")
    assert catalog.get("english_companion").input_policy == "external_text"
    assert catalog.get("shorten_content").input_policy == "contextual_text"
    assert "preserve the original language of each part" in catalog.get("shorten_content").system_prompt
    assert "Never translate" in catalog.get("shorten_content").system_prompt
    assert "English input must produce English only" in catalog.get("shorten_content").system_prompt
    assert "structure absent from the input" in catalog.get("shorten_content").system_prompt
    assert "as briefly as possible" in catalog.resolve("shorten_content", "long").prompt
    assert "freely merge paragraphs and remove line breaks" in catalog.resolve("shorten_content", "long").prompt


@pytest.mark.parametrize(
    ("shortcut", "message"),
    (
        ({"id": "x", "hotkey": "ctrl+alt+x", "command": "unknown"}, "command"),
        ({"id": "x", "hotkey": "ctrl+alt+x", "command": "start_action"}, "action_id"),
        ({"id": "x", "hotkey": "ctrl+alt+x", "command": "start_action", "action_id": "missing"}, "unknown action"),
    ),
)
def test_invalid_shortcut_is_rejected(tmp_path: Path, shortcut: dict, message: str) -> None:
    import yaml

    path = tmp_path / "shortcuts.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "shortcuts": [shortcut]}), encoding="utf-8")
    actions = load_action_catalog("config/actions.yaml")
    with pytest.raises(ConfigError, match=message):
        load_shortcut_catalog(path, actions=actions)


def test_duplicate_shortcut_hotkey_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "shortcuts.yaml"
    path.write_text(
        """schema_version: 1
shortcuts:
  - id: one
    hotkey: ctrl+alt+q
    command: speak_selection_or_clipboard
  - id: two
    hotkey: CTRL+ALT+Q
    command: speak_selection_or_clipboard
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate shortcut hotkey"):
        load_shortcut_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_provider_readiness_is_nonfatal_and_secret_repr_is_redacted() -> None:
    bundle = load_config_bundle()
    credential = ProviderCredential("GEMINI_API_KEY")
    issues = assess_provider_readiness(bundle.providers, credential)
    assert issues[0].code == "provider.missing_api_key"
    assert "GEMINI_API_KEY" in issues[0].message
    assert "secret-value" not in repr(ProviderCredential("KEY", "secret-value"))
