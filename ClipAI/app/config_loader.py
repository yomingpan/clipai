from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar, cast

import yaml

from ClipAI.app.config_schema import AppSettings, ConfigBundle, ConfigSchemaVersions, ModifierMode, ProviderCatalog, ProviderName, RuntimeSettings, TTSSettings, VoiceInputSettings, VoiceOpenAISettings
from ClipAI.core.errors import ConfigError
from ClipAI.core.models import ActionDefinition, ActionVariant, InputMode, InputPolicy, OutputMode, OutputProfile, PressType, ShortcutCommandKind, ShortcutDefinition
from ClipAI.providers.settings import AnthropicSettings, GeminiSettings, OpenAISettings
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.output_profiles import OutputProfileCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.support.logging_setup import Diagnostics, LoggingSettings

T = TypeVar("T")
CURRENT_SCHEMA_VERSION = 1
ACTIONS_SCHEMA_VERSION = 3


def load_config_bundle(
    *,
    app_config_path: str | Path = "config/config.yaml",
    actions_path: str | Path = "config/actions.yaml",
    shortcuts_path: str | Path = "config/shortcuts.yaml",
    output_profiles_path: str | Path = "config/output_profiles.yaml",
) -> ConfigBundle:
    app, runtime, providers, tts, voice_input, logging_settings = load_app_config(app_config_path)
    output_profiles = load_output_profiles(output_profiles_path)
    actions = load_action_catalog(actions_path, output_profiles=output_profiles)
    shortcuts = load_shortcut_catalog(shortcuts_path, actions=actions)
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
        schema_versions=ConfigSchemaVersions(
            app=_read_schema_version(app_config_path),
            actions=_read_schema_version(actions_path, max_version=ACTIONS_SCHEMA_VERSION),
            output_profiles=_read_schema_version(output_profiles_path),
            shortcuts=_read_schema_version(shortcuts_path),
        ),
    )


def load_app_config(path: str | Path) -> tuple[AppSettings, RuntimeSettings, ProviderCatalog, TTSSettings, VoiceInputSettings, LoggingSettings]:
    root = _load_yaml_mapping(path)
    _schema_version(root, path)
    _reject_unknown(root, {"schema_version", "app", "provider", "runtime", "tts", "voice_input", "logging"}, "config")
    app_data = _mapping(root.get("app"), "config.app")
    _reject_unknown(app_data, {"stream", "temperature", "system_prompt", "modifier_mode"}, "config.app")
    app = AppSettings(
        stream=_boolean(app_data.get("stream"), "config.app.stream", default=False),
        temperature=_number(app_data.get("temperature"), "config.app.temperature", default=0.2),
        system_prompt=_string(app_data.get("system_prompt"), "config.app.system_prompt", default=""),
        modifier_mode=cast(ModifierMode, _choice(app_data.get("modifier_mode"), "config.app.modifier_mode", {"alt_shift", "ctrl_shift", "ctrl_alt"}, "ctrl_alt")),
    )

    runtime_data = _mapping(root.get("runtime"), "config.runtime", allow_none=True)
    _reject_unknown(runtime_data, {"max_workers"}, "config.runtime")
    max_workers = _integer(runtime_data.get("max_workers"), "config.runtime.max_workers", default=2)
    if max_workers < 1:
        raise ConfigError("config.runtime.max_workers must be at least 1")
    runtime = RuntimeSettings(max_workers=max_workers)

    provider_data = _mapping(root.get("provider"), "config.provider")
    _reject_unknown(provider_data, {"active", "gemini", "openai", "anthropic"}, "config.provider")
    active = cast(ProviderName, _choice(provider_data.get("active"), "config.provider.active", {"fake", "gemini", "openai", "anthropic"}, "fake"))
    providers = ProviderCatalog(
        active=active,
        gemini=_parse_gemini(_mapping(provider_data.get("gemini"), "config.provider.gemini")),
        openai=_parse_openai(_mapping(provider_data.get("openai"), "config.provider.openai")),
        anthropic=_parse_anthropic(_mapping(provider_data.get("anthropic"), "config.provider.anthropic")),
    )
    return app, runtime, providers, _parse_tts(root.get("tts")), _parse_voice_input(root.get("voice_input")), _parse_logging(root.get("logging"))


def _parse_tts(value: Any) -> TTSSettings:
    path = "config.tts"
    data = _mapping(value, path, allow_none=True)
    _reject_unknown(data, {"enabled", "voice", "english_voice", "rate", "volume"}, path)
    return TTSSettings(
        enabled=_boolean(data.get("enabled"), f"{path}.enabled", default=False),
        voice=_string(data.get("voice"), f"{path}.voice", default=""),
        rate=_string(data.get("rate"), f"{path}.rate", default="+0%"),
        volume=_string(data.get("volume"), f"{path}.volume", default="+0%"),
        english_voice=_string(data.get("english_voice"), f"{path}.english_voice", default="en-US-AndrewNeural"),
    )


def _parse_voice_input(value: Any) -> VoiceInputSettings:
    path = "config.voice_input"
    data = _mapping(value, path, allow_none=True)
    allowed = {"backend", "browser", "host", "port", "allow_port_fallback", "language", "auto_start", "clipboard_mode", "openai"}
    _reject_unknown(data, allowed, path)
    openai_path = f"{path}.openai"
    openai = _mapping(data.get("openai"), openai_path, allow_none=True)
    _reject_unknown(openai, {"api_key_env", "base_url", "model", "language", "timeout_sec"}, openai_path)
    return VoiceInputSettings(
        backend=_string(data.get("backend"), f"{path}.backend", default="browser_speech"),
        browser=_string(data.get("browser"), f"{path}.browser", default="edge"),
        host=_string(data.get("host"), f"{path}.host", default="127.0.0.1"),
        port=_integer(data.get("port"), f"{path}.port", default=8765),
        allow_port_fallback=_boolean(data.get("allow_port_fallback"), f"{path}.allow_port_fallback", default=True),
        language=_string(data.get("language"), f"{path}.language", default="zh-TW"),
        auto_start=_boolean(data.get("auto_start"), f"{path}.auto_start", default=False),
        clipboard_mode=_string(data.get("clipboard_mode"), f"{path}.clipboard_mode", default="replace_full_text"),
        openai=VoiceOpenAISettings(
            api_key_env=_string(openai.get("api_key_env"), f"{openai_path}.api_key_env", default="OPENAI_API_KEY"),
            base_url=_string(openai.get("base_url"), f"{openai_path}.base_url", default="https://api.openai.com/v1"),
            model=_string(openai.get("model"), f"{openai_path}.model", default="whisper-1"),
            language=_string(openai.get("language"), f"{openai_path}.language", default="zh"),
            timeout_sec=_positive_number(openai.get("timeout_sec"), f"{openai_path}.timeout_sec", 60),
        ),
    )


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


def load_output_profiles(path: str | Path) -> OutputProfileCatalog:
    payload = _load_yaml_mapping(path)
    _schema_version(payload, path)
    _reject_unknown(payload, {"schema_version", "profiles"}, "output_profiles")
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ConfigError("output_profiles.profiles must be a list")
    profiles: list[OutputProfile] = []
    for index, value in enumerate(raw_profiles):
        profile_path = f"output_profiles.profiles[{index}]"
        data = _mapping(value, profile_path)
        _reject_unknown(data, {"id", "instruction", "required_markers", "presentation"}, profile_path)
        markers = data.get("required_markers", [])
        if not isinstance(markers, list) or not all(isinstance(marker, str) and marker.strip() for marker in markers):
            raise ConfigError(f"{profile_path}.required_markers must be a list of non-empty strings")
        profiles.append(OutputProfile(
            id=_string(data.get("id"), f"{profile_path}.id"),
            instruction=_string(data.get("instruction"), f"{profile_path}.instruction", default=""),
            required_markers=tuple(marker.strip() for marker in markers),
            presentation=_string(data.get("presentation"), f"{profile_path}.presentation", default="plain_text"),
        ))
    return OutputProfileCatalog(profiles)


def load_action_catalog(path: str | Path, *, output_profiles: OutputProfileCatalog | None = None) -> ActionCatalog:
    output_profiles = output_profiles or load_output_profiles("config/output_profiles.yaml")
    payload = _load_yaml_mapping(path)
    _schema_version(payload, path, max_version=ACTIONS_SCHEMA_VERSION)
    _reject_unknown(payload, {"schema_version", "actions"}, "actions")
    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, list):
        raise ConfigError("actions.actions must be a list")
    actions = [_parse_action(item, index) for index, item in enumerate(raw_actions)]
    for action in actions:
        profile_ids = [action.output_profile, *(variant.output_profile for variant in action.press_variants.values() if variant.output_profile)]
        for profile_id in profile_ids:
            if not output_profiles.contains(profile_id):
                raise ConfigError(f"action {action.id} references unknown output profile: {profile_id}")
    return ActionCatalog(actions)


def _parse_action(value: Any, index: int) -> ActionDefinition:
    path = f"actions.actions[{index}]"
    data = _mapping(value, path)
    allowed = {"id", "name", "system_prompt", "prompt", "press_variants", "stream", "input_mode", "input_policy", "output_mode", "temperature", "output_profile"}
    _reject_unknown(data, allowed, path)
    variants: dict[PressType, ActionVariant] = {}
    raw_variants = _mapping(data.get("press_variants"), f"{path}.press_variants", allow_none=True)
    _reject_unknown(raw_variants, {"short", "long"}, f"{path}.press_variants")
    for press_type in ("short", "long"):
        if press_type not in raw_variants:
            continue
        variant_path = f"{path}.press_variants.{press_type}"
        variant = _mapping(raw_variants[press_type], variant_path)
        _reject_unknown(variant, {"name", "system_prompt", "prompt", "output_profile"}, variant_path)
        variants[cast(PressType, press_type)] = ActionVariant(
            name=_string(variant.get("name"), f"{variant_path}.name"),
            system_prompt=_string(variant.get("system_prompt"), f"{variant_path}.system_prompt"),
            prompt=_string(variant.get("prompt"), f"{variant_path}.prompt"),
            output_profile=_string(variant.get("output_profile"), f"{variant_path}.output_profile", default="") or None,
        )
    temperature = data.get("temperature")
    return ActionDefinition(
        id=_string(data.get("id"), f"{path}.id"),
        name=_string(data.get("name"), f"{path}.name"),
        system_prompt=_string(data.get("system_prompt"), f"{path}.system_prompt"),
        prompt=_string(data.get("prompt"), f"{path}.prompt"),
        press_variants=variants,
        stream=_boolean(data.get("stream"), f"{path}.stream", default=False),
        input_mode=cast(InputMode, _choice(data.get("input_mode"), f"{path}.input_mode", {"clipboard", "selection_or_clipboard"}, "clipboard")),
        output_mode=cast(OutputMode, _choice(data.get("output_mode"), f"{path}.output_mode", {"popup"}, "popup")),
        temperature=None if temperature is None else _number(temperature, f"{path}.temperature"),
        output_profile=_string(data.get("output_profile"), f"{path}.output_profile", default="plain_text"),
        input_policy=cast(InputPolicy, _choice(data.get("input_policy"), f"{path}.input_policy", {"external_text", "contextual_text"}, "external_text")),
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
        command = cast(ShortcutCommandKind, _choice(data.get("command"), f"{shortcut_path}.command", {"start_action", "speak_selection_or_clipboard"}, "start_action"))
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
        elif action_id is not None:
            raise ConfigError(f"{shortcut_path}.action_id is only supported for start_action")
        ids.add(shortcut_id)
        hotkeys.add(hotkey)
        shortcuts.append(ShortcutDefinition(shortcut_id, hotkey, command, action_id))
    return ShortcutCatalog(shortcuts)


def _parse_gemini(data: dict[str, Any]) -> GeminiSettings:
    path = "config.provider.gemini"
    _reject_unknown(data, {"api_key_env", "base_url", "model", "timeout_sec"}, path)
    return GeminiSettings(
        api_key_env=_string(data.get("api_key_env"), f"{path}.api_key_env", default="GEMINI_API_KEY"),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="https://generativelanguage.googleapis.com"),
        model=_string(data.get("model"), f"{path}.model", default="gemini-2.0-flash"),
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
    )


def _parse_openai(data: dict[str, Any]) -> OpenAISettings:
    path = "config.provider.openai"
    _reject_unknown(data, {"api_key_env", "base_url", "model", "timeout_sec"}, path)
    return OpenAISettings(
        api_key_env=_string(data.get("api_key_env"), f"{path}.api_key_env", default="OPENAI_API_KEY"),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="https://api.openai.com"),
        model=_string(data.get("model"), f"{path}.model", default="gpt-4.1-mini"),
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
    )


def _parse_anthropic(data: dict[str, Any]) -> AnthropicSettings:
    path = "config.provider.anthropic"
    _reject_unknown(data, {"api_key_env", "base_url", "model", "timeout_sec", "api_version", "max_tokens"}, path)
    return AnthropicSettings(
        api_key_env=_string(data.get("api_key_env"), f"{path}.api_key_env", default="ANTHROPIC_API_KEY"),
        base_url=_string(data.get("base_url"), f"{path}.base_url", default="https://api.anthropic.com"),
        model=_string(data.get("model"), f"{path}.model", default="claude-sonnet-4-5"),
        timeout_sec=_positive_number(data.get("timeout_sec"), f"{path}.timeout_sec", 60.0),
        api_version=_string(data.get("api_version"), f"{path}.api_version", default="2023-06-01"),
        max_tokens=_positive_integer(data.get("max_tokens"), f"{path}.max_tokens", default=1024),
    )


def _load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return _mapping(yaml.safe_load(handle) or {}, str(path))
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


def _string(value: Any, path: str, *, default: str | None = None) -> str:
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or (not value.strip() and default is None):
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
