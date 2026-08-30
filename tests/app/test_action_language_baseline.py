from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from string import Formatter
from typing import Any

import yaml

from ClipAI.app.config_loader import load_config_bundle


ROOT = Path(__file__).parents[2]
CONFIG_DIR = ROOT / "config"
BASELINE_PATH = ROOT / "tests" / "fixtures" / "action_language" / "zh_tw_baseline_hashes.json"


def _load_yaml(name: str) -> dict[str, Any]:
    payload = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _current_baseline() -> dict[str, Any]:
    action_payload = _load_yaml("actions.yaml")
    profile_payload = _load_yaml("output_profiles.yaml")
    bundle = load_config_bundle(
        app_config_path=CONFIG_DIR / "config.yaml",
        actions_path=CONFIG_DIR / "actions.yaml",
        shortcuts_path=CONFIG_DIR / "shortcuts.yaml",
        output_profiles_path=CONFIG_DIR / "output_profiles.yaml",
        entry_panel_path=CONFIG_DIR / "entry_panel.yaml",
    )

    action_ids = [action["id"] for action in action_payload["actions"]]
    explicit_variants = [
        f"{action['id']}:{press_type}"
        for action in action_payload["actions"]
        for press_type in action.get("press_variants", {})
    ]
    profile_ids = [profile["id"] for profile in profile_payload["profiles"]]
    shortcuts = [asdict(shortcut) for shortcut in bundle.shortcuts.definitions()]

    return {
        "schema_version": 1,
        "inventory": {
            "actions": len(action_ids),
            "explicit_variants": explicit_variants,
            "output_profiles": len(profile_ids),
            "shortcuts": len(shortcuts),
            "start_action_shortcuts": sum(
                shortcut["command"] == "start_action" for shortcut in shortcuts
            ),
        },
        "default_system_prompt": _digest(bundle.app.system_prompt),
        "resolved_actions": {
            f"{action_id}:{press_type}": _digest(
                asdict(bundle.actions.resolve(action_id, press_type))
            )
            for action_id in action_ids
            for press_type in ("short", "long")
        },
        "output_profiles": {
            profile_id: _digest(asdict(bundle.output_profiles.get(profile_id)))
            for profile_id in profile_ids
        },
        "shortcut_matrix": _digest(shortcuts),
    }


def test_action_language_inventory_and_prompt_contract_are_frozen() -> None:
    action_payload = _load_yaml("actions.yaml")
    shortcut_payload = _load_yaml("shortcuts.yaml")
    profile_payload = _load_yaml("output_profiles.yaml")
    actions = action_payload["actions"]
    explicit_variants = [
        variant
        for action in actions
        for variant in action.get("press_variants", {}).values()
    ]

    assert len(actions) == 27
    assert len(explicit_variants) == 6
    assert len(shortcut_payload["shortcuts"]) == 30
    assert sum(
        shortcut["command"] == "start_action"
        for shortcut in shortcut_payload["shortcuts"]
    ) == 27
    assert len(profile_payload["profiles"]) == 10

    prompts = [action["prompt"] for action in actions]
    prompts.extend(variant["prompt"] for variant in explicit_variants)
    for prompt in prompts:
        fields = [field for _, field, _, _ in Formatter().parse(prompt) if field]
        assert fields == ["input"]


def test_effective_zh_tw_action_language_baseline_is_unchanged() -> None:
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert _current_baseline() == expected
