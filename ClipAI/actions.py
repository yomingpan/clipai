from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

import yaml

logger = logging.getLogger(__name__)

PressType = Literal["short", "long"]

_SUPPORTED_PRESS_TYPES = {"short", "long"}
_FORBIDDEN_VARIANT_KEYS = {"id", "hotkey", "press_variants"}
_ALLOWED_VARIANT_KEYS = {
    "name",
    "prompt",
    "prompt_file",
    "system_prompt",
    "system_prompt_file",
    "template",
    "input_mode",
    "output_mode",
    "stream",
    "temperature",
    "model",
    "provider",
    "hedge_enabled",
    "hedge_secondary_provider",
    "hedge_secondary_model",
    "hedge_delay_ms",
}


@dataclass(frozen=True)
class ResolvedAction:
    action_id: str
    press_type: PressType
    action_def: dict[str, Any]
    variant_applied: bool

    @property
    def action_name(self) -> str:
        return str(self.action_def.get("name") or self.action_id)


def load_config(path: str):
    """Load the main configuration file (provider, app, tts settings)."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def _resolve_prompt_file_refs(target: dict[str, Any], base_dir: str) -> dict[str, Any]:
    for file_key, content_key in (
        ("prompt_file", "prompt"),
        ("system_prompt_file", "system_prompt"),
    ):
        file_ref = target.get(file_key)
        if not file_ref:
            continue
        full_path = os.path.join(base_dir, str(file_ref))
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    target[content_key] = f.read()
            except Exception as exc:
                logger.warning("Failed to read prompt file %s: %s", full_path, exc)
                target[content_key] = ""
        else:
            logger.warning(
                "Prompt file not found: %s (referenced by action '%s')",
                full_path,
                target.get("id", "unknown"),
            )
            target[content_key] = ""
        del target[file_key]
    return target


def _normalize_press_variants(action: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_variants = action.get("press_variants")
    if raw_variants is None:
        return {}
    if not isinstance(raw_variants, dict):
        raise ValueError(f"Action '{action.get('id', 'unknown')}' press_variants must be a mapping.")

    normalized: dict[str, dict[str, Any]] = {}
    for press_type, override in raw_variants.items():
        if press_type not in _SUPPORTED_PRESS_TYPES:
            raise ValueError(
                f"Action '{action.get('id', 'unknown')}' has unsupported press variant '{press_type}'."
            )
        if not isinstance(override, dict):
            raise ValueError(
                f"Action '{action.get('id', 'unknown')}' variant '{press_type}' must be a mapping."
            )
        forbidden = sorted(_FORBIDDEN_VARIANT_KEYS.intersection(override))
        if forbidden:
            raise ValueError(
                f"Action '{action.get('id', 'unknown')}' variant '{press_type}' cannot override: {', '.join(forbidden)}."
            )
        unknown = sorted(set(override) - _ALLOWED_VARIANT_KEYS)
        if unknown:
            raise ValueError(
                f"Action '{action.get('id', 'unknown')}' variant '{press_type}' has unsupported keys: {', '.join(unknown)}."
            )
        normalized[press_type] = copy.deepcopy(override)
    return normalized


def normalize_actions(actions: list[dict[str, Any]] | None, base_dir: str) -> list[dict[str, Any]]:
    normalized_actions: list[dict[str, Any]] = []
    for raw_action in actions or []:
        if not isinstance(raw_action, dict):
            raise ValueError("Each action must be a mapping.")
        action = copy.deepcopy(raw_action)
        _resolve_prompt_file_refs(action, base_dir)

        variants = _normalize_press_variants(action)
        for override in variants.values():
            _resolve_prompt_file_refs(override, base_dir)
        if variants:
            action["press_variants"] = variants
        elif "press_variants" in action:
            del action["press_variants"]

        normalized_actions.append(action)
    return normalized_actions


def resolve_action_variant(action_def: dict[str, Any], press_type: PressType = "short") -> ResolvedAction:
    if press_type not in _SUPPORTED_PRESS_TYPES:
        raise ValueError(f"Unsupported press type: {press_type}")

    base_action = copy.deepcopy(action_def)
    variants = copy.deepcopy(base_action.pop("press_variants", {}) or {})
    override = variants.get(press_type) or {}
    merged_action = copy.deepcopy(base_action)
    merged_action.update(copy.deepcopy(override))
    return ResolvedAction(
        action_id=str(base_action.get("id") or "action-default"),
        press_type=press_type,
        action_def=merged_action,
        variant_applied=bool(override),
    )


def load_actions(config_path: str):
    """Load action definitions from actions.yaml (or fall back to config.yaml)."""
    config_dir = os.path.dirname(os.path.abspath(config_path))
    actions_path = os.path.join(config_dir, "actions.yaml")

    if os.path.isfile(actions_path):
        with open(actions_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        actions = data.get("actions")
        if actions is not None:
            return normalize_actions(actions, config_dir)

    cfg = load_config(config_path)
    actions = cfg.get("actions", [])
    return normalize_actions(actions, config_dir)


def build_action_map(actions):
    out = {}
    for a in actions or []:
        action_id = a.get("id")
        if not action_id:
            continue
        out[action_id] = a
    return out
