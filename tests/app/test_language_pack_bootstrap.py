from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

import pytest
import yaml

from ClipAI.app.language_pack_bootstrap import bootstrap_action_language_config
from ClipAI.core.errors import ActionLanguagePackError
from ClipAI.core.models import ActionLanguagePackSelectionRead


@dataclass
class SelectionStore:
    selected_pack_id: str | None = None
    diagnostic_code: str = ""
    saves: list[str] | None = None

    def load(self) -> ActionLanguagePackSelectionRead:
        return ActionLanguagePackSelectionRead(
            self.selected_pack_id,
            self.diagnostic_code,
        )

    def save(self, pack_id: str) -> None:
        if self.saves is not None:
            self.saves.append(pack_id)


def _copy_config(tmp_path: Path) -> Path:
    destination = tmp_path / "config"
    shutil.copytree("config", destination)
    return destination


def _bootstrap(config_dir: Path, store: SelectionStore):
    return bootstrap_action_language_config(
        store,
        app_config_path=config_dir / "config.yaml",
        actions_path=config_dir / "actions.yaml",
        shortcuts_path=config_dir / "shortcuts.yaml",
        output_profiles_path=config_dir / "output_profiles.yaml",
        entry_panel_path=config_dir / "entry_panel.yaml",
    )


def _register_broken_pack(config_dir: Path, pack_id: str = "broken") -> None:
    registry_path = config_dir / "language_packs.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["packs"].append(
        {"pack_id": pack_id, "path": f"language_packs/{pack_id}"}
    )
    registry_path.write_text(
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    shutil.copytree(
        config_dir / "language_packs" / "zh-TW",
        config_dir / "language_packs" / pack_id,
    )


def test_missing_selection_bootstraps_default_without_rewriting_store(tmp_path) -> None:
    config_dir = _copy_config(tmp_path)
    saves: list[str] = []

    result = _bootstrap(config_dir, SelectionStore(saves=saves))

    assert result.bundle.action_language.identity.pack_id == "zh-TW"
    assert result.state.active_pack.pack_id == "zh-TW"
    assert result.state.selected_pack_id == "zh-TW"
    assert result.state.recovery is None
    assert saves == []


def test_missing_selected_pack_falls_back_without_changing_selection(tmp_path) -> None:
    config_dir = _copy_config(tmp_path)

    result = _bootstrap(config_dir, SelectionStore("ja-JP"))

    assert result.bundle.action_language.identity.pack_id == "zh-TW"
    assert result.state.active_pack.pack_id == "zh-TW"
    assert result.state.selected_pack_id == "ja-JP"
    assert result.state.recovery is not None
    assert result.state.recovery.reason == "pack_missing"


def test_invalid_nondefault_pack_is_omitted_from_availability(tmp_path) -> None:
    config_dir = _copy_config(tmp_path)
    _register_broken_pack(config_dir)

    result = _bootstrap(config_dir, SelectionStore())

    assert tuple(
        descriptor.identity.pack_id for descriptor in result.state.available_packs
    ) == ("zh-TW",)
    assert "action_language_pack.broken.manifest_invalid" in result.diagnostic_codes


def test_invalid_selected_pack_falls_back_as_one_complete_default_catalog(
    tmp_path,
) -> None:
    config_dir = _copy_config(tmp_path)
    _register_broken_pack(config_dir)

    result = _bootstrap(config_dir, SelectionStore("broken"))

    assert result.state.selected_pack_id == "broken"
    assert result.state.recovery is not None
    assert result.state.recovery.reason == "manifest_invalid"
    assert result.bundle.action_language.identity.pack_id == "zh-TW"
    assert result.bundle.actions.get("english_companion").name == "English Companion"


def test_invalid_default_pack_remains_a_fatal_startup_error(tmp_path) -> None:
    config_dir = _copy_config(tmp_path)
    manifest = config_dir / "language_packs" / "zh-TW" / "manifest.yaml"
    manifest.write_text("schema_version: 1\n", encoding="utf-8")

    with pytest.raises(ActionLanguagePackError) as caught:
        _bootstrap(config_dir, SelectionStore())

    assert caught.value.reason == "manifest_invalid"


def test_corrupt_selection_diagnostic_uses_default_without_recovery(tmp_path) -> None:
    config_dir = _copy_config(tmp_path)

    result = _bootstrap(
        config_dir,
        SelectionStore(None, "action_language.selection_invalid"),
    )

    assert result.state.selected_pack_id == "zh-TW"
    assert result.state.recovery is None
    assert result.diagnostic_codes == ("action_language.selection_invalid",)
