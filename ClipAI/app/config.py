from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from ClipAI.platform.hotkey import PressType


@dataclass(frozen=True)
class ActionPrompt:
    name: str
    system_prompt: str
    prompt: str


@dataclass(frozen=True)
class ActionConfig:
    id: str
    name: str
    hotkey: str
    system_prompt: str
    prompt: str
    press_variants: dict[PressType, ActionPrompt]


@dataclass(frozen=True)
class ResolvedAction:
    id: str
    name: str
    system_prompt: str
    prompt: str
    press_type: PressType


@dataclass(frozen=True)
class AppConfig:
    default_model: str
    temperature: float
    modifier_mode: Literal["alt_shift", "ctrl_shift", "ctrl_alt"] = "ctrl_alt"


class ActionCatalog:
    def __init__(self, actions: list[ActionConfig]) -> None:
        self._actions = {action.id: action for action in actions}

    def get(self, action_id: str) -> ActionConfig:
        try:
            return self._actions[action_id]
        except KeyError as exc:
            raise ValueError(f"unknown action: {action_id}") from exc

    def resolve(self, action_id: str, press_type: PressType) -> ResolvedAction:
        action = self.get(action_id)
        variant = action.press_variants.get(press_type)
        if variant is None:
            return ResolvedAction(
                id=action.id,
                name=action.name,
                system_prompt=action.system_prompt,
                prompt=action.prompt,
                press_type=press_type,
            )
        return ResolvedAction(
            id=action.id,
            name=variant.name,
            system_prompt=variant.system_prompt,
            prompt=variant.prompt,
            press_type=press_type,
        )

    def hotkey_action_map(self) -> dict[str, dict[str, str]]:
        return {
            action.id: {"hotkey": action.hotkey}
            for action in self._actions.values()
            if action.hotkey.strip()
        }


@dataclass(frozen=True)
class ConfigBundle:
    app: AppConfig
    actions: ActionCatalog


def load_config_bundle(
    *,
    app_config_path: str | Path = "config/config.yaml",
    actions_path: str | Path = "config/actions.yaml",
) -> ConfigBundle:
    return ConfigBundle(
        app=load_app_config(app_config_path),
        actions=load_action_catalog(actions_path),
    )


def load_app_config(path: str | Path) -> AppConfig:
    payload = _load_yaml_mapping(path)
    app_payload = _mapping(payload.get("app"))
    provider_payload = _mapping(payload.get("provider"))
    return AppConfig(
        default_model=str(provider_payload.get("default_model") or "fake-model"),
        temperature=float(app_payload.get("temperature", 0.2)),
    )


def load_action_catalog(path: str | Path) -> ActionCatalog:
    payload = _load_yaml_mapping(path)
    raw_actions = payload.get("actions") or []
    if not isinstance(raw_actions, list):
        raise ValueError("actions.yaml must contain an actions list")
    actions = [_parse_action(item) for item in raw_actions]
    return ActionCatalog(actions)


def _parse_action(item: Any) -> ActionConfig:
    data = _mapping(item)
    action_id = _required_str(data, "id")
    press_variants = _parse_press_variants(data.get("press_variants"))
    return ActionConfig(
        id=action_id,
        name=_required_str(data, "name"),
        hotkey=str(data.get("hotkey") or ""),
        system_prompt=_required_str(data, "system_prompt"),
        prompt=_required_str(data, "prompt"),
        press_variants=press_variants,
    )


def _parse_press_variants(value: Any) -> dict[PressType, ActionPrompt]:
    variants: dict[PressType, ActionPrompt] = {}
    raw = _mapping(value) if value else {}
    for press_type in ("short", "long"):
        if press_type not in raw:
            continue
        data = _mapping(raw[press_type])
        variants[press_type] = ActionPrompt(
            name=str(data.get("name") or ""),
            system_prompt=_required_str(data, "system_prompt"),
            prompt=_required_str(data, "prompt"),
        )
    return variants


def _load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return _mapping(yaml.safe_load(fh) or {})


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected mapping")
    return value


def _required_str(data: dict[str, Any], key: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing required action field: {key}")
    return value
