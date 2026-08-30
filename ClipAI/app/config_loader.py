from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import yaml

from ClipAI.app.config_yaml import UniqueKeyLoader
from ClipAI.app.language_pack_loader import ActionLanguagePackLoader, load_feature_skeleton
from ClipAI.app.config_schema import AppSettings, ConfigBundle, ConfigSchemaVersions, ModifierMode, ProviderCatalog, ProviderName, RuntimeSettings, TTSSettings, VoiceInputSettings
from ClipAI.core.errors import ConfigError
from ClipAI.core.models import EntryActionRef, PressType, ShortcutCommandKind, ShortcutDefinition
from ClipAI.providers.settings import AnthropicSettings, GatewaySettings, GeminiSettings, OpenAISettings
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.action_language_packs import CompiledActionLanguagePack
from ClipAI.services.entry_panel import EntryPanelCandidate, EntryPanelCatalog, EntryPanelCategory
from ClipAI.services.output_profiles import OutputProfileCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.support.logging_setup import Diagnostics, LoggingSettings

T = TypeVar("T")
CURRENT_SCHEMA_VERSION = 1
APP_CONFIG_SCHEMA_VERSION = 2
ACTIONS_SCHEMA_VERSION = 11
OUTPUT_PROFILES_SCHEMA_VERSION = 2


def load_config_bundle(
    *,
    app_config_path: str | Path = "config/config.yaml",
    actions_path: str | Path = "config/actions.yaml",
    shortcuts_path: str | Path = "config/shortcuts.yaml",
    output_profiles_path: str | Path = "config/output_profiles.yaml",
    entry_panel_path: str | Path = "config/entry_panel.yaml",
    action_language_pack: CompiledActionLanguagePack | None = None,
) -> ConfigBundle:
    app, runtime, providers, tts, voice_input, logging_settings = load_app_config(app_config_path)
    config_dir = Path(actions_path).parent
    compiled_pack = action_language_pack
    if compiled_pack is None:
        skeleton = load_feature_skeleton(
            config_dir,
            actions_path=actions_path,
            shortcuts_path=shortcuts_path,
            output_profiles_path=output_profiles_path,
        )
        language_pack_loader = ActionLanguagePackLoader(config_dir, skeleton)
        language_pack_registry = language_pack_loader.load_registry()
        compiled_pack = language_pack_loader.load(
            language_pack_registry.entry(language_pack_registry.default_pack_id)
        )
    app = replace(app, system_prompt=compiled_pack.default_system_prompt)
    output_profiles = OutputProfileCatalog(list(compiled_pack.output_profiles))
    actions = ActionCatalog(
        list(compiled_pack.action_definitions),
        default_stream=app.stream,
        version_context=compiled_pack.version_context,
    )
    shortcuts = load_shortcut_catalog(shortcuts_path, actions=actions)
    entry_panel = load_entry_panel_catalog(entry_panel_path, actions=actions)
    return ConfigBundle(
        app=app,
        runtime=runtime,
        providers=providers,
        actions=actions,
        shortcuts=shortcuts,
        tts=tts,
        voice_input=voice_input,
        logging=logging_settings,
        output_profiles=output_profiles,
        entry_panel=entry_panel,
        action_language=compiled_pack.provenance,
        schema_versions=ConfigSchemaVersions(
            app=_read_schema_version(app_config_path, max_version=APP_CONFIG_SCHEMA_VERSION),
            actions=_read_schema_version(actions_path, max_version=ACTIONS_SCHEMA_VERSION),
            output_profiles=_read_schema_version(
                output_profiles_path,
                max_version=OUTPUT_PROFILES_SCHEMA_VERSION,
            ),
            shortcuts=_read_schema_version(shortcuts_path),
            entry_panel=_read_schema_version(entry_panel_path),
            action_language_registry=1,
            action_language_manifest=1,
            action_language_resources=1,
        ),
    )


def load_app_config(path: str | Path) -> tuple[AppSettings, RuntimeSettings, ProviderCatalog, TTSSettings, VoiceInputSettings, LoggingSettings]:
    root = _load_yaml_mapping(path)
    _schema_version(root, path, max_version=APP_CONFIG_SCHEMA_VERSION)
    _reject_unknown(root, {"schema_version", "app", "provider", "runtime", "tts", "voice_input", "logging"}, "config")
    app_data = _mapping(root.get("app"), "config.app")
    _reject_unknown(app_data, {"stream", "temperature", "modifier_mode", "entry_panel_enabled"}, "config.app")
    app = AppSettings(
        stream=_boolean(app_data.get("stream"), "config.app.stream", default=False),
        temperature=_number(app_data.get("temperature"), "config.app.temperature", default=0.2),
        system_prompt="",
        modifier_mode=cast(ModifierMode, _choice(app_data.get("modifier_mode"), "config.app.modifier_mode", {"alt_shift", "ctrl_shift", "ctrl_alt"}, "ctrl_alt")),
        entry_panel_enabled=_boolean(app_data.get("entry_panel_enabled"), "config.app.entry_panel_enabled", default=False),
    )

    runtime_data = _mapping(root.get("runtime"), "config.runtime", allow_none=True)
    _reject_unknown(runtime_data, {"maintenance_workers", "max_workers"}, "config.runtime")
    if "maintenance_workers" in runtime_data and "max_workers" in runtime_data:
        raise ConfigError("config.runtime must not define both maintenance_workers and legacy max_workers")
    field = "max_workers" if "max_workers" in runtime_data else "maintenance_workers"
    maintenance_workers = _integer(runtime_data.get(field), f"config.runtime.{field}", default=1)
    if maintenance_workers < 1:
        raise ConfigError(f"config.runtime.{field} must be at least 1")
    runtime = RuntimeSettings(maintenance_workers=maintenance_workers)

    provider_data = _mapping(root.get("provider"), "config.provider")
    _reject_unknown(provider_data, {"active", "gemini", "openai", "anthropic", "gateway"}, "config.provider")
    active = cast(ProviderName, _choice(provider_data.get("active"), "config.provider.active", {"fake", "gemini", "openai", "anthropic", "gateway"}, "fake"))
    providers = ProviderCatalog(
        active=active,
        gemini=_parse_gemini(_mapping(provider_data.get("gemini"), "config.provider.gemini")),
        openai=_parse_openai(_mapping(provider_data.get("openai"), "config.provider.openai")),
        anthropic=_parse_anthropic(_mapping(provider_data.get("anthropic"), "config.provider.anthropic")),
        gateway=_parse_gateway(_mapping(provider_data.get("gateway"), "config.provider.gateway", allow_none=True)),
    )
    return app, runtime, providers, _parse_tts(root.get("tts")), _parse_voice_input(root.get("voice_input")), _parse_logging(root.get("logging"))


def _parse_tts(value: Any) -> TTSSettings:
    path = "config.tts"
    data = _mapping(value, path, allow_none=True)
    _reject_unknown(data, {"enabled", "voice", "english_voice", "japanese_voice", "rate", "volume"}, path)
    return TTSSettings(
        enabled=_boolean(data.get("enabled"), f"{path}.enabled", default=False),
        voice=_string(data.get("voice"), f"{path}.voice", default=""),
        rate=_string(data.get("rate"), f"{path}.rate", default="+0%"),
        volume=_string(data.get("volume"), f"{path}.volume", default="+0%"),
        english_voice=_string(data.get("english_voice"), f"{path}.english_voice", default="en-US-AndrewNeural"),
        japanese_voice=_string(data.get("japanese_voice"), f"{path}.japanese_voice", default="ja-JP-NanamiNeural"),
    )


def _parse_voice_input(value: Any) -> VoiceInputSettings:
    path = "config.voice_input"
    data = _mapping(value, path, allow_none=True)
    _reject_unknown(data, {"backend"}, path)
    backend = _choice(
        data.get("backend"),
        f"{path}.backend",
        {"edge_webview2_browser_speech"},
        "edge_webview2_browser_speech",
    )
    return VoiceInputSettings(backend=cast(Literal["edge_webview2_browser_speech"], backend))


def _parse_logging(value: Any) -> LoggingSettings:
    path = "config.logging"
    data = _mapping(value, path, allow_none=True)
    allowed = {"enabled", "level", "console", "console_level", "file_enabled", "file_path", "file_level", "module_levels", "diagnostics"}
    _reject_unknown(data, allowed, path)
    module_levels = _mapping(data.get("module_levels"), f"{path}.module_levels", allow_none=True)
    diagnostics = _mapping(data.get("diagnostics"), f"{path}.diagnostics", allow_none=True)
    enabled_flags = frozenset(name for name, enabled in diagnostics.items() if _boolean(enabled, f"{path}.diagnostics.{name}", default=False))
    return LoggingSettings(
        enabled=_boolean(data.get("enabled"), f"{path}.enabled", default=True),
        level=_logging_level(data.get("level"), f"{path}.level", default="INFO"),
        console=_boolean(data.get("console"), f"{path}.console", default=False),
        console_level=_logging_level(data.get("console_level"), f"{path}.console_level", default="INFO"),
        file_enabled=_boolean(data.get("file_enabled"), f"{path}.file_enabled", default=True),
        file_path=_string(data.get("file_path"), f"{path}.file_path", default="logs/clipai.log"),
        file_level=_logging_level(data.get("file_level"), f"{path}.file_level", default="DEBUG"),
        module_levels=tuple((str(name), _logging_level(level, f"{path}.module_levels.{name}")) for name, level in module_levels.items()),
        diagnostics=Diagnostics(enabled_flags),
    )


def load_shortcut_catalog(path: str | Path, *, actions: ActionCatalog) -> ShortcutCatalog:
    payload = _load_yaml_mapping(path)
    _schema_version(payload, path)
    _reject_unknown(payload, {"schema_version", "shortcuts"}, "shortcuts")
    raw_shortcuts = payload.get("shortcuts")
    if not isinstance(raw_shortcuts, list):
        raise ConfigError("shortcuts.shortcuts must be a list")
    shortcuts: list[ShortcutDefinition] = []
    hotkeys: set[str] = set()
    ids: set[str] = set()
    for index, value in enumerate(raw_shortcuts):
        shortcut_path = f"shortcuts.shortcuts[{index}]"
        data = _mapping(value, shortcut_path)
        _reject_unknown(data, {"id", "hotkey", "command", "action_id"}, shortcut_path)
        shortcut_id = _string(data.get("id"), f"{shortcut_path}.id")
        hotkey = _string(data.get("hotkey"), f"{shortcut_path}.hotkey").lower()
        command = cast(ShortcutCommandKind, _choice(data.get("command"), f"{shortcut_path}.command", {"start_action", "open_contextual_question", "speak_selection_or_clipboard", "push_to_talk"}, "start_action"))
        action_id = _string(data.get("action_id"), f"{shortcut_path}.action_id", default="") or None
        if shortcut_id in ids:
            raise ConfigError(f"duplicate shortcut id: {shortcut_id}")
        if hotkey in hotkeys:
            raise ConfigError(f"duplicate shortcut hotkey: {hotkey}")
        if command == "start_action":
            if action_id is None:
                raise ConfigError(f"{shortcut_path}.action_id is required for start_action")
            if not actions.contains(action_id):
                raise ConfigError(f"{shortcut_path}.action_id references unknown action: {action_id}")
            if actions.get(action_id).feedback_contract is None:
                raise ConfigError(f"{shortcut_path}.action_id must reference an action with feedback enabled")
        elif action_id is not None:
            raise ConfigError(f"{shortcut_path}.action_id is only valid for start_action")
        ids.add(shortcut_id)
        hotkeys.add(hotkey)
        shortcuts.append(ShortcutDefinition(shortcut_id, hotkey, command, action_id))
    return ShortcutCatalog(shortcuts)


def load_entry_panel_catalog(path: str | Path, *, actions: ActionCatalog) -> EntryPanelCatalog:
    payload = _load_yaml_mapping(path)
    _schema_version(payload, path)
    _reject_unknown(payload, {"schema_version", "categories"}, "entry_panel")
    raw_categories = payload.get("categories")
    if not isinstance(raw_categories, list):
        raise ConfigError("entry_panel.categories must be a list")
    categories: list[EntryPanelCategory] = []
    for index, value in enumerate(raw_categories):
        category_path = f"entry_panel.categories[{index}]"
        data = _mapping(value, category_path)
        _reject_unknown(data, {"id", "slot", "label", "description", "flagship", "advanced"}, category_path)
        slot = _integer(data.get("slot"), f"{category_path}.slot", default=0)
        category_id = _string(data.get("id"), f"{category_path}.id")
        flagship = _parse_entry_panel_candidates(data.get("flagship"), f"{category_path}.flagship")
        advanced = _parse_entry_panel_candidates(data.get("advanced"), f"{category_path}.advanced")
        categories.append(EntryPanelCategory(
            category_id=category_id,
            slot=slot,
            label=_string(data.get("label"), f"{category_path}.label"),
            description=_string(data.get("description"), f"{category_path}.description"),
            flagship=flagship,
            advanced=advanced,
        ))
    try:
        return EntryPanelCatalog(tuple(categories), actions=actions)
    except ValueError as error:
        raise ConfigError(str(error)) from error


def _parse_entry_panel_candidates(
    value: Any,
    path: str,
) -> tuple[EntryPanelCandidate, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list")
    candidates: list[EntryPanelCandidate] = []
    for index, item in enumerate(value):
        candidate_path = f"{path}[{index}]"
        data = _mapping(item, candidate_path)
        _reject_unknown(data, {"action_id", "press_type", "label", "description"}, candidate_path)
        action_id = _string(data.get("action_id"), f"{candidate_path}.action_id")
        press_type = cast(PressType, _choice(data.get("press_type"), f"{candidate_path}.press_type", {"short", "long"}, "short"))
        candidates.append(EntryPanelCandidate(
            EntryActionRef(action_id, press_type),
            _string(data.get("label"), f"{candidate_path}.label"),
            _string(data.get("description"), f"{candidate_path}.description"),
        ))
    return tuple(candidates)


def _parse_gemini(data: dict[str, Any]) -> GeminiSettings:
    path = "config.provider.gemini"
    _reject_unknown(data, {"api_key_env", "base_url", "model", "available_models", "timeout_sec"}, path)
    model = _string(data.get("model"), f"{path}.model", default="gemini-2.0-flash")
    available_models = _model_catalog(data.get("available_models"), f"{path}.available_models", model)
    return GeminiSettings(
        api_key_env=_string(data.get("api_key_env"), f"{path}.api_key_env", default="GEMINI_API_KEY"),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="https://generativelanguage.googleapis.com"),
        model=model,
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
        available_models=available_models,
    )


def _parse_openai(data: dict[str, Any]) -> OpenAISettings:
    path = "config.provider.openai"
    _reject_unknown(data, {"api_key_env", "base_url", "model", "available_models", "timeout_sec"}, path)
    model = _string(data.get("model"), f"{path}.model", default="gpt-4.1-mini")
    available_models = _model_catalog(data.get("available_models"), f"{path}.available_models", model)
    return OpenAISettings(
        api_key_env=_string(data.get("api_key_env"), f"{path}.api_key_env", default="OPENAI_API_KEY"),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="https://api.openai.com"),
        model=model,
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
        available_models=available_models,
    )


def _parse_anthropic(data: dict[str, Any]) -> AnthropicSettings:
    path = "config.provider.anthropic"
    _reject_unknown(data, {"api_key_env", "base_url", "model", "available_models", "timeout_sec", "api_version", "max_tokens"}, path)
    model = _string(data.get("model"), f"{path}.model", default="claude-sonnet-4-5")
    available_models = _model_catalog(data.get("available_models"), f"{path}.available_models", model)
    return AnthropicSettings(
        api_key_env=_string(data.get("api_key_env"), f"{path}.api_key_env", default="ANTHROPIC_API_KEY"),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="https://api.anthropic.com"),
        model=model,
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
        api_version=_string(data.get("api_version"), f"{path}.api_version", default="2023-06-01"),
        max_tokens=_positive_integer(data.get("max_tokens"), f"{path}.max_tokens", default=1024),
        available_models=available_models,
    )


def _parse_gateway(data: dict[str, Any]) -> GatewaySettings:
    path = "config.provider.gateway"
    _reject_unknown(data, {"name", "base_url", "model", "timeout_sec"}, path)
    model = _string(data.get("model"), f"{path}.model", default="", allow_empty=True)
    return GatewaySettings(
        name=_string(data.get("name"), f"{path}.name", default="Custom Gateway", allow_empty=True),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="", allow_empty=True),
        model=model,
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
        available_models=(model,) if model else (),
    )


def _model_catalog(value: Any, path: str, default_model: str) -> tuple[str, ...]:
    if value is None:
        return (default_model,)
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list of non-empty model names")
    models: list[str] = []
    for index, item in enumerate(value):
        model = _string(item, f"{path}[{index}]")
        if model in models:
            raise ConfigError(f"{path} contains duplicate model: {model}")
        models.append(model)
    if not models:
        raise ConfigError(f"{path} must contain at least one model")
    if default_model not in models:
        raise ConfigError(f"{path} must include configured model: {default_model}")
    return tuple(models)


def _load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return _mapping(yaml.load(handle, Loader=UniqueKeyLoader) or {}, str(path))
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc


def _read_schema_version(path: str | Path, *, max_version: int = CURRENT_SCHEMA_VERSION) -> int:
    return _schema_version(_load_yaml_mapping(path), path, max_version=max_version)


def _schema_version(data: dict[str, Any], path: str | Path, *, max_version: int = CURRENT_SCHEMA_VERSION) -> int:
    """Treat unversioned documents as legacy v0 without rewriting them."""
    value = data.get("schema_version", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"{path}.schema_version must be a non-negative integer")
    if value > max_version:
        raise ConfigError(
            f"{path} uses schema_version {value}; this ClipAI supports up to {max_version}"
        )
    return value


def _mapping(value: Any, path: str, *, allow_none: bool = False) -> dict[str, Any]:
    if value is None and allow_none:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be a mapping")
    return value


def _reject_unknown(data: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"{path}.{unknown[0]} is not a supported setting")


def _string(value: Any, path: str, *, default: str | None = None, allow_empty: bool = False) -> str:
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or (not value.strip() and default is None and not allow_empty):
        raise ConfigError(f"{path} must be a non-empty string")
    return value.strip()


def _boolean(value: Any, path: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{path} must be true or false")
    return value


def _number(value: Any, path: str, *, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    return float(value)


def _positive_number(value: Any, path: str, default: float) -> float:
    result = _number(value, path, default=default)
    if result <= 0:
        raise ConfigError(f"{path} must be greater than zero")
    return result


def _integer(value: Any, path: str, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path} must be an integer")
    return value


def _positive_integer(value: Any, path: str, *, default: int) -> int:
    result = _integer(value, path, default=default)
    if result < 1:
        raise ConfigError(f"{path} must be at least 1")
    return result


def _choice(value: Any, path: str, choices: set[str], default: str) -> str:
    result = _string(value, path, default=default).lower()
    if result not in choices:
        raise ConfigError(f"{path} must be one of: {', '.join(sorted(choices))}")
    return result


def _logging_level(value: Any, path: str, default: str | None = None) -> str:
    result = _string(value, path, default=default).upper()
    allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
    if result not in allowed:
        raise ConfigError(f"{path} must be one of: {', '.join(sorted(allowed))}")
    return result
