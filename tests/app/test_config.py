from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.app.config_loader import load_action_catalog, load_app_config, load_config_bundle, load_output_profiles
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
    assert bundle.output_profiles.get(action.output_profile).required_markers == ("Synonym:",)
    assert bundle.schema_versions.app == 1
    assert bundle.schema_versions.actions == 1
    assert bundle.schema_versions.output_profiles == 1


def test_long_press_uses_variant_prompt() -> None:
    resolved = load_action_catalog("config/actions.yaml").resolve("english_companion", "long")
    assert resolved.name == "英文改善建議"
    assert "Improve the following English" in resolved.prompt
    assert resolved.output_profile == "english_improvement"


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
    (("actions.yaml", load_action_catalog), ("output_profiles.yaml", load_output_profiles)),
)
def test_future_catalog_schema_version_is_rejected(tmp_path: Path, filename: str, loader) -> None:
    path = tmp_path / filename
    path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"{filename}.*schema_version 2"):
        loader(path)


def test_provider_readiness_is_nonfatal_and_secret_repr_is_redacted() -> None:
    bundle = load_config_bundle()
    credential = ProviderCredential("GEMINI_API_KEY")
    issues = assess_provider_readiness(bundle.providers, credential)
    assert issues[0].code == "provider.missing_api_key"
    assert "GEMINI_API_KEY" in issues[0].message
    assert "secret-value" not in repr(ProviderCredential("KEY", "secret-value"))
