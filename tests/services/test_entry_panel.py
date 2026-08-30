from ClipAI.app.config_loader import load_action_catalog, load_entry_panel_catalog
import pytest

from ClipAI.core.models import EntryActionRef, EntryPanelSelectionId
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.entry_panel import EntryPanelCandidate, EntryPanelCatalog, EntryPanelCategory, EntryPanelCoordinator


def coordinator() -> EntryPanelCoordinator:
    return EntryPanelCoordinator(load_entry_panel_catalog(
        "config/entry_panel.yaml",
        actions=load_action_catalog("config/actions.yaml"),
    ))


def test_root_digit_opens_configured_scene_with_flagship_slots() -> None:
    panel = coordinator()
    root = panel.open("panel-1")

    scene_decision = panel.select_digit("3")
    action_decision = panel.select_digit("1")
    scene = scene_decision.snapshot

    assert root.page == "root"
    assert scene.page == "scene"
    assert scene.category_id == "understand"
    assert tuple(option.slot for option in scene.options) == (1, 2, 3, 4)
    assert scene.options[0].action.action_id == "translate_to_traditional_chinese"
    assert action_decision.action == EntryActionRef("translate_to_traditional_chinese", "short")
    assert action_decision.snapshot == scene


def test_root_projects_only_available_recent_actions_into_zero_based_slots() -> None:
    panel = coordinator()

    root = panel.open(
        "panel-1",
        recent=(
            EntryActionRef("shorten_content", "short"),
            EntryActionRef("english_companion", "short"),
        ),
    )

    recent = tuple(option for option in root.options if option.action is not None)
    assert tuple(option.slot for option in recent) == (0, 1)
    assert tuple(option.action.action_id for option in recent) == (
        "shorten_content",
        "english_companion",
    )


def test_more_and_escape_follow_the_progressive_navigation_stack() -> None:
    panel = coordinator()
    panel.open("panel-1")
    scene = panel.select_digit("5").snapshot

    more = panel.open_more()
    returned_scene = panel.escape()
    returned_root = panel.escape()
    closed = panel.escape()

    assert scene.page == "scene"
    assert more.page == "more"
    assert more.category_id == "think"
    assert all(option.slot is None for option in more.options)
    assert returned_scene.page == "scene"
    assert returned_root.page == "root"
    assert closed is None


def test_search_filters_only_the_current_more_page() -> None:
    panel = coordinator()
    panel.open("panel-1")
    panel.select_digit("5")
    panel.open_more()

    filtered = panel.set_search("MECE")

    assert filtered.page == "more"
    assert filtered.search_text == "MECE"
    assert tuple(option.action.action_id for option in filtered.options) == (
        "mece_decomposition",
    )


def test_density_toggle_preserves_page_search_and_action_order() -> None:
    panel = coordinator()
    panel.open("panel-1")
    panel.select_digit("5")
    panel.open_more()
    detailed = panel.set_search("name")

    compact = panel.toggle_density()

    assert compact.density == "compact"
    assert compact.page == detailed.page
    assert compact.category_id == detailed.category_id
    assert compact.search_text == detailed.search_text
    assert compact.options == detailed.options
    assert panel.toggle_density().density == "detailed"


def test_open_reuses_the_preferred_density_for_the_next_panel_lifecycle() -> None:
    panel = EntryPanelCoordinator(
        load_entry_panel_catalog("config/entry_panel.yaml", actions=load_action_catalog("config/actions.yaml")),
        density="compact",
    )

    first = panel.open("panel-1")
    panel.close()
    second = panel.open("panel-2")

    assert first.density == "compact"
    assert second.density == "compact"


def test_disabled_action_stays_visible_with_reason_and_cannot_be_selected() -> None:
    panel = coordinator()
    action = EntryActionRef("translate_to_english", "short")
    panel.open(
        "panel-1",
        disabled={action: "請先完成 Personal Style 設定"},
    )
    scene = panel.select_digit("4").snapshot

    decision = panel.select_digit("1")

    assert scene.options[0].enabled is False
    assert scene.options[0].disabled_reason == "請先完成 Personal Style 設定"
    assert decision.action is None


def test_preparation_identity_rejects_late_completion_after_replacement() -> None:
    panel = coordinator()
    panel.open("panel-1")
    first = EntryPanelSelectionId("selection-1")
    second = EntryPanelSelectionId("selection-2")

    panel.begin_preparation(first)
    pending = panel.begin_preparation(second)
    stale = panel.settle_preparation(first, message="stale failure")
    settled = panel.settle_preparation(second, message="target unavailable")

    assert pending.status == "preparing"
    assert pending.selection_id == second
    assert stale is None
    assert settled.status == "error"
    assert settled.message == "target unavailable"
    assert settled.selection_id is None


def test_close_invalidates_active_preparation_identity() -> None:
    panel = coordinator()
    panel.open("panel-1")
    selection_id = EntryPanelSelectionId("selection-1")
    panel.begin_preparation(selection_id)

    panel.close()

    assert panel.snapshot is None
    assert panel.settle_preparation(selection_id) is None


def test_catalog_rejects_semantically_invalid_categories_without_yaml_loader() -> None:
    with pytest.raises(ValueError, match="slot must be one of: 3, 4, 5, 6"):
        EntryPanelCatalog(
            (
                EntryPanelCategory(
                    "invalid",
                    2,
                    "Invalid",
                    "Invalid",
                    (EntryPanelCandidate(EntryActionRef("unknown", "short"), "Unknown", ""),),
                    (),
                ),
            ),
            actions=ActionCatalog([]),
        )


def test_catalog_rejects_unknown_action_without_yaml_loader() -> None:
    with pytest.raises(ValueError, match="unknown entry action: unknown/short"):
        EntryPanelCatalog(
            (
                EntryPanelCategory(
                    "understand",
                    3,
                    "Understand",
                    "Understand",
                    (EntryPanelCandidate(EntryActionRef("unknown", "short"), "Unknown", ""),),
                    (),
                ),
            ),
            actions=ActionCatalog([]),
        )
