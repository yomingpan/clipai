from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.app.config_loader import load_action_catalog, load_app_config, load_config_bundle
from ClipAI.core.errors import ConfigError


def test_config_bundle_loads_typed_provider_and_action_settings() -> None:
    bundle = load_config_bundle()

    assert bundle.providers.active == "gemini"
    assert bundle.providers.gemini.model == "gemma-4-31b-it"
    assert bundle.runtime.max_workers == 2
    assert bundle.app.modifier_mode == "ctrl_alt"
    action = bundle.actions.get("english_companion")
    assert action.input_mode == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is False
    assert action.temperature == 0.2


def test_long_press_uses_variant_prompt() -> None:
    resolved = load_action_catalog("config/actions.yaml").resolve("english_companion", "long")
    assert resolved.name == "英文改善建議"
    assert "Improve the following English" in resolved.prompt


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
