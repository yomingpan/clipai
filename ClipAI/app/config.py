from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clipai.actions import build_action_map, load_actions, load_config


@dataclass(frozen=True)
class AppConfigBundle:
    config_path: str
    cfg: dict[str, Any]
    app_cfg: dict[str, Any]
    provider_cfg: dict[str, Any]
    tts_cfg: dict[str, Any]
    actions: list[dict[str, Any]]
    action_map: dict[str, dict[str, Any]]


def load_app_config(config_path: str = "config/config.yaml") -> AppConfigBundle:
    cfg = load_config(config_path)
    actions = load_actions(config_path)
    return AppConfigBundle(
        config_path=config_path,
        cfg=cfg,
        app_cfg=dict(cfg.get("app", {}) or {}),
        provider_cfg=dict(cfg.get("provider", {}) or {}),
        tts_cfg=dict(cfg.get("tts", {}) or {}),
        actions=actions,
        action_map=build_action_map(actions),
    )
