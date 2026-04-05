from __future__ import annotations

from pathlib import Path

import pytest

from clipai.actions import normalize_actions, resolve_action_variant


def test_resolve_action_variant_defaults_short_to_base_action() -> None:
    action = {
        "id": "summarize",
        "name": "Summary",
        "prompt": "Base {input}",
        "output_mode": "popup",
    }

    resolved = resolve_action_variant(action, "short")

    assert resolved.action_id == "summarize"
    assert resolved.press_type == "short"
    assert resolved.variant_applied is False
    assert resolved.action_def["prompt"] == "Base {input}"
    assert resolved.action_def["output_mode"] == "popup"


def test_resolve_action_variant_merges_long_override() -> None:
    action = {
        "id": "summarize",
        "name": "Summary",
        "prompt": "Base {input}",
        "output_mode": "popup",
        "press_variants": {
            "long": {
                "name": "Explain",
                "prompt": "Explain {input}",
            }
        },
    }

    resolved = resolve_action_variant(action, "long")

    assert resolved.action_name == "Explain"
    assert resolved.variant_applied is True
    assert resolved.action_def["prompt"] == "Explain {input}"
    assert resolved.action_def["output_mode"] == "popup"


def test_normalize_actions_rejects_variant_hotkey_override(tmp_path: Path) -> None:
    actions = [
        {
            "id": "summarize",
            "hotkey": "ctrl+alt+5",
            "prompt": "{input}",
            "press_variants": {
                "long": {
                    "hotkey": "ctrl+alt+6",
                    "prompt": "Explain {input}",
                }
            },
        }
    ]

    with pytest.raises(ValueError, match="cannot override: hotkey"):
        normalize_actions(actions, str(tmp_path))


def test_normalize_actions_resolves_prompt_files_inside_variants(tmp_path: Path) -> None:
    prompt_path = tmp_path / "explain.txt"
    prompt_path.write_text("Explain this:\n{input}", encoding="utf-8")
    actions = [
        {
            "id": "summarize",
            "hotkey": "ctrl+alt+5",
            "prompt": "Base {input}",
            "press_variants": {
                "long": {
                    "prompt_file": "explain.txt",
                    "output_mode": "popup",
                }
            },
        }
    ]

    normalized = normalize_actions(actions, str(tmp_path))

    assert normalized[0]["press_variants"]["long"]["prompt"] == "Explain this:\n{input}"
    assert "prompt_file" not in normalized[0]["press_variants"]["long"]
