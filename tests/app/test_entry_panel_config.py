from pathlib import Path

import pytest

from ClipAI.app.config_loader import load_action_catalog, load_config_bundle, load_entry_panel_catalog
from ClipAI.core.errors import ConfigError
from ClipAI.core.models import EntryActionRef


def test_entry_panel_catalog_compiles_configured_category_and_candidate(tmp_path: Path) -> None:
    path = tmp_path / "entry_panel.yaml"
    path.write_text(
        """
schema_version: 1
categories:
  - id: understand
    slot: 3
    label: 看得懂
    description: 這段內容到底在說什麼？
    flagship:
      - action_id: english_companion
        press_type: long
        label: English Companion
        description: 理解英文
    advanced: []
""".strip(),
        encoding="utf-8",
    )

    catalog = load_entry_panel_catalog(
        path,
        actions=load_action_catalog("config/actions.yaml"),
    )

    category = catalog.category_for_slot(3)
    assert category.label == "看得懂"
    assert category.flagship[0].action == EntryActionRef("english_companion", "long")


def test_entry_panel_catalog_rejects_duplicate_root_slots(tmp_path: Path) -> None:
    path = tmp_path / "entry_panel.yaml"
    path.write_text(
        """
schema_version: 1
categories:
  - id: understand
    slot: 3
    label: 看得懂
    description: 理解
    flagship: []
    advanced: []
  - id: write
    slot: 3
    label: 寫得出
    description: 表達
    flagship: []
    advanced: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="duplicate category slot: 3"):
        load_entry_panel_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_entry_panel_catalog_limits_scene_to_four_flagships(tmp_path: Path) -> None:
    path = tmp_path / "entry_panel.yaml"
    candidates = "\n".join(
        f"      - action_id: {action_id}\n        press_type: short\n        label: {action_id}\n        description: item"
        for action_id in (
            "english_companion",
            "reading_friction",
            "explain_like_friend",
            "article_structure",
            "extract_keywords",
        )
    )
    path.write_text(
        "\n".join((
            "schema_version: 1",
            "categories:",
            "  - id: understand",
            "    slot: 3",
            "    label: 看得懂",
            "    description: 理解",
            "    flagship:",
            candidates,
            "    advanced: []",
        )),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="flagship must contain at most 4 candidates"):
        load_entry_panel_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_entry_panel_catalog_rejects_duplicate_action_reference(tmp_path: Path) -> None:
    path = tmp_path / "entry_panel.yaml"
    path.write_text(
        """
schema_version: 1
categories:
  - id: understand
    slot: 3
    label: 看得懂
    description: 理解
    flagship:
      - action_id: english_companion
        press_type: short
        label: English Companion
        description: 理解英文
    advanced:
      - action_id: english_companion
        press_type: short
        label: English Companion
        description: 理解英文
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="duplicate entry action: english_companion/short"):
        load_entry_panel_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_entry_panel_catalog_reserves_root_slots_three_through_six(tmp_path: Path) -> None:
    path = tmp_path / "entry_panel.yaml"
    path.write_text(
        """
schema_version: 1
categories:
  - id: invalid
    slot: 2
    label: Invalid
    description: Invalid
    flagship: []
    advanced: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="slot must be one of: 3, 4, 5, 6"):
        load_entry_panel_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_entry_panel_catalog_rejects_duplicate_category_ids(tmp_path: Path) -> None:
    path = tmp_path / "entry_panel.yaml"
    path.write_text(
        """
schema_version: 1
categories:
  - id: understand
    slot: 3
    label: 看得懂
    description: 理解
    flagship: []
    advanced: []
  - id: understand
    slot: 4
    label: 寫得出
    description: 表達
    flagship: []
    advanced: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="duplicate category id: understand"):
        load_entry_panel_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_product_entry_panel_catalog_matches_prd_order() -> None:
    catalog = load_entry_panel_catalog(
        "config/entry_panel.yaml",
        actions=load_action_catalog("config/actions.yaml"),
    )

    expected = {
        3: (
            "understand",
            ("translate_to_traditional_chinese", "english_companion", "explain_like_friend", "reading_friction"),
            ("article_structure", "extract_keywords"),
        ),
        4: (
            "write",
            ("translate_to_english", "shorten_content", "personal_style_informal", "intent_preserving_dictation_editor"),
            ("expression_retrieval", "personal_style_oral", "personal_style_presentation"),
        ),
        5: (
            "think",
            ("pyramid_position", "critical_thinking", "tradeoff_perspective", "reflective_question"),
            (
                "name_idea",
                "name_concept_carefully",
                "illuminate_essence",
                "temporary_viewpoint",
                "mece_decomposition",
                "minimum_action",
                "structure_score_prompt",
            ),
        ),
        6: (
            "tools",
            ("extract_screenshot_text", "session_handoff", "command_copilot"),
            (),
        ),
    }
    actual = {
        category.slot: (
            category.category_id,
            tuple(item.action.action_id for item in category.flagship),
            tuple(item.action.action_id for item in category.advanced),
        )
        for category in catalog.categories
    }

    assert actual == expected
    assert all(
        item.action.press_type == "short"
        for category in catalog.categories
        for item in (*category.flagship, *category.advanced)
    )


def test_config_bundle_exposes_disabled_entry_panel_catalog() -> None:
    bundle = load_config_bundle()

    assert bundle.app.entry_panel_enabled is True
    assert bundle.entry_panel.category_for_slot(3).category_id == "understand"
    assert bundle.schema_versions.entry_panel == 1
