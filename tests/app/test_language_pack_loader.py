from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from ClipAI.app.language_pack_loader import (
    ActionLanguagePackLoader,
    load_feature_skeleton,
    validate_official_language_packs,
)
from ClipAI.core.errors import ActionLanguagePackError
from ClipAI.services.action_language_packs import feature_contract_hash
from scripts.validate_language_packs import main as validator_main


def _write_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _build_valid_config(root: Path) -> Path:
    config = root / "config"
    _write_yaml(
        config / "actions.yaml",
        {
            "schema_version": 11,
            "actions": [
                {
                    "id": "explain",
                    "stream": True,
                    "input_mode": "selection_or_clipboard",
                    "external_fallback": "selection_or_clipboard",
                    "output_mode": "popup",
                    "temperature": 0.2,
                    "output_profile": "structured",
                    "prompt_variables": ["input"],
                    "feedback_reason_ids": ["incorrect", "other"],
                    "press_variants": {
                        "long": {
                            "prompt_variables": ["input"],
                        },
                    },
                },
            ],
        },
    )
    _write_yaml(
        config / "shortcuts.yaml",
        {
            "schema_version": 1,
            "shortcuts": [
                {
                    "id": "explain",
                    "hotkey": "ctrl+alt+e",
                    "command": "start_action",
                    "action_id": "explain",
                },
            ],
        },
    )
    _write_yaml(
        config / "output_profiles.yaml",
        {
            "schema_version": 2,
            "profiles": [
                {"id": "plain_text", "presentation": "plain_text"},
                {
                    "id": "structured",
                    "presentation": "markdown_sections",
                    "markers": [
                        {"marker_id": "heading", "kind": "localized"},
                        {
                            "marker_id": "scroll_break",
                            "kind": "control_token",
                            "literal": "[[SCROLL_BREAK]]",
                        },
                    ],
                },
            ],
        },
    )
    _write_yaml(
        config / "entry_panel.yaml",
        {
            "schema_version": 2,
            "categories": [
                {
                    "id": "understand",
                    "slot": 3,
                    "label": "看得懂",
                    "description": "理解內容",
                    "flagship": [
                        {"action_id": "explain", "press_type": "short"},
                    ],
                    "advanced": [],
                },
            ],
        },
    )
    pack = config / "language_packs" / "zh-TW"
    resources = {
        "app": {
            "schema_version": 1,
            "default_system_prompt": "你是一位有幫助的助理。",
        },
        "actions": {
            "schema_version": 1,
            "actions": {
                "explain": {
                    "name": "解釋",
                    "system_prompt": "忠實解釋輸入。",
                    "prompt": "請解釋：{input}",
                    "feedback": {
                        "helps": "幫你解釋",
                        "does_not": "不替你判斷",
                        "reasons": {
                            "incorrect": "內容不正確",
                            "other": "其他",
                        },
                    },
                    "variants": {
                        "long": {
                            "name": "詳細解釋",
                            "system_prompt": "忠實且詳細地解釋輸入。",
                            "prompt": "請詳細解釋：{input}",
                        },
                    },
                },
            },
        },
        "output_profiles": {
            "schema_version": 1,
            "profiles": {
                "plain_text": {"instruction": ""},
                "structured": {
                    "instruction": "使用指定段落。",
                    "markers": {"heading": "## 解釋"},
                },
            },
        },
        "entry_panel": {
            "schema_version": 1,
            "candidates": [
                {
                    "action_id": "explain",
                    "press_type": "short",
                    "label": "快速解釋",
                    "description": "用清楚的方式說明內容。",
                },
            ],
        },
    }
    resource_entries: dict[str, dict[str, str]] = {}
    for name, payload in resources.items():
        path = pack / f"{name}.yaml"
        _write_yaml(path, payload)
        resource_entries[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    skeleton = load_feature_skeleton(config)
    _write_yaml(
        pack / "manifest.yaml",
        {
            "schema_version": 1,
            "pack_id": "zh-TW",
            "locale": "zh-TW",
            "display_name": "繁體中文",
            "pack_version": "1.0.0",
            "feature_contract_hash": feature_contract_hash(skeleton),
            "resources": resource_entries,
        },
    )
    _write_yaml(
        config / "language_packs.yaml",
        {
            "schema_version": 1,
            "default_pack_id": "zh-TW",
            "packs": [
                {"pack_id": "zh-TW", "path": "language_packs/zh-TW"},
            ],
        },
    )
    return config


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _refresh_checksum(config: Path, resource_name: str) -> None:
    pack = config / "language_packs" / "zh-TW"
    manifest_path = pack / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    resource_path = pack / manifest["resources"][resource_name]["path"]
    manifest["resources"][resource_name]["sha256"] = hashlib.sha256(
        resource_path.read_bytes()
    ).hexdigest()
    _write_yaml(manifest_path, manifest)


def _assert_failure(config: Path, reason: str) -> ActionLanguagePackError:
    with pytest.raises(ActionLanguagePackError) as caught:
        validate_official_language_packs(config)
    assert caught.value.reason == reason
    assert caught.value.path
    return caught.value


def test_loader_validates_and_compiles_every_official_pack(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)

    packs = validate_official_language_packs(config)

    assert len(packs) == 1
    assert packs[0].descriptor.identity.pack_id == "zh-TW"
    assert packs[0].action_definitions[0].name == "解釋"
    assert packs[0].output_profiles[1].required_markers == (
        "## 解釋",
        "[[SCROLL_BREAK]]",
    )
    assert packs[0].entry_panel_candidates[0].label == "快速解釋"


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_manifest_requires_exact_entry_panel_resource_set(
    tmp_path: Path,
    mutation: str,
) -> None:
    config = _build_valid_config(tmp_path)
    manifest_path = config / "language_packs" / "zh-TW" / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    if mutation == "missing":
        del manifest["resources"]["entry_panel"]
    else:
        manifest["resources"]["extra"] = manifest["resources"]["app"].copy()
    _write_yaml(manifest_path, manifest)

    _assert_failure(config, "manifest_invalid")


def test_entry_panel_resource_inventory_is_checked_against_canonical_refs(
    tmp_path: Path,
) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs" / "zh-TW" / "entry_panel.yaml"
    payload = _load_yaml(path)
    payload["candidates"] = []
    _write_yaml(path, payload)
    _refresh_checksum(config, "entry_panel")

    _assert_failure(config, "inventory_mismatch")


def test_registry_order_is_preserved_as_product_order(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)
    skeleton = load_feature_skeleton(config)
    loader = ActionLanguagePackLoader(config, skeleton)

    registry = loader.load_registry()

    assert tuple(entry.pack_id for entry in registry.packs) == ("zh-TW",)
    assert registry.entry("zh-TW") == registry.packs[0]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("duplicate", "registry_invalid"),
        ("default_missing", "registry_invalid"),
        ("absolute", "registry_invalid"),
        ("parent", "registry_invalid"),
    ),
)
def test_registry_rejects_duplicate_missing_default_and_escaping_paths(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs.yaml"
    registry = _load_yaml(path)
    if mutation == "duplicate":
        registry["packs"].append(registry["packs"][0].copy())
    elif mutation == "default_missing":
        registry["default_pack_id"] = "missing"
    elif mutation == "absolute":
        registry["packs"][0]["path"] = str((tmp_path / "outside").resolve())
    else:
        registry["packs"][0]["path"] = "../outside"
    _write_yaml(path, registry)

    _assert_failure(config, reason)


def test_checksum_is_verified_before_yaml_parse(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs" / "zh-TW" / "actions.yaml"
    path.write_text("not: [valid", encoding="utf-8")

    _assert_failure(config, "checksum_mismatch")


def test_invalid_utf8_is_rejected_after_matching_checksum(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs" / "zh-TW" / "actions.yaml"
    path.write_bytes(b"\xff\xfe")
    _refresh_checksum(config, "actions")

    _assert_failure(config, "inventory_mismatch")


@pytest.mark.parametrize("missing", ("manifest", "resource"))
def test_missing_manifest_or_resource_has_stable_error(
    tmp_path: Path,
    missing: str,
) -> None:
    config = _build_valid_config(tmp_path)
    pack = config / "language_packs" / "zh-TW"
    target = pack / ("manifest.yaml" if missing == "manifest" else "actions.yaml")
    target.unlink()

    _assert_failure(config, "pack_missing")


@pytest.mark.parametrize("resource_path", ("../actions.yaml", "C:/outside/actions.yaml"))
def test_resource_paths_must_remain_inside_pack_root(
    tmp_path: Path,
    resource_path: str,
) -> None:
    config = _build_valid_config(tmp_path)
    manifest_path = config / "language_packs" / "zh-TW" / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    manifest["resources"]["actions"]["path"] = resource_path
    _write_yaml(manifest_path, manifest)

    _assert_failure(config, "resource_path_invalid")


def test_manifest_identity_must_match_registry_and_directory(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)
    manifest_path = config / "language_packs" / "zh-TW" / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    manifest["pack_id"] = "ja-JP"
    _write_yaml(manifest_path, manifest)

    _assert_failure(config, "manifest_invalid")


def test_duplicate_yaml_keys_are_not_silently_overwritten(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)
    manifest_path = config / "language_packs" / "zh-TW" / "manifest.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "pack_id: duplicate\n",
        encoding="utf-8",
    )

    _assert_failure(config, "manifest_invalid")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("presentation", "markdown_sections", "inventory_mismatch"),
        ("temperature", 0.9, "inventory_mismatch"),
    ),
)
def test_pack_action_resources_cannot_provide_behavior_fields(
    tmp_path: Path,
    field: str,
    value: object,
    reason: str,
) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs" / "zh-TW" / "actions.yaml"
    payload = _load_yaml(path)
    payload["actions"]["explain"][field] = value
    _write_yaml(path, payload)
    _refresh_checksum(config, "actions")

    _assert_failure(config, reason)


def test_pack_profile_cannot_localize_control_token(tmp_path: Path) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs" / "zh-TW" / "output_profiles.yaml"
    payload = _load_yaml(path)
    payload["profiles"]["structured"]["markers"]["scroll_break"] = "可翻譯"
    _write_yaml(path, payload)
    _refresh_checksum(config, "output_profiles")

    _assert_failure(config, "marker_contract_mismatch")


def test_validator_cli_and_loader_report_the_same_typed_error_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _build_valid_config(tmp_path)
    path = config / "language_packs" / "zh-TW" / "actions.yaml"
    path.write_text("corrupt", encoding="utf-8")

    error = _assert_failure(config, "checksum_mismatch")
    assert validator_main(["--config-dir", str(config)]) == 2

    output = capsys.readouterr().out
    assert output.startswith(f"{error.reason}: {error.path}")
