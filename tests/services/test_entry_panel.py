from ClipAI.app.config_loader import load_config_bundle
import pytest

from ClipAI.core.models import EntryActionRef, EntryInputSourcePreview
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.entry_panel import EntryPanelCandidate, EntryPanelCatalog, EntryPanelCategory, EntryPanelCoordinator


def coordinator() -> EntryPanelCoordinator:
    return EntryPanelCoordinator(load_config_bundle().entry_panel)


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


def test_more_and_back_follow_the_progressive_navigation_stack_without_closing_root() -> None:
    panel = coordinator()
    panel.open("panel-1")
    scene = panel.select_digit("5").snapshot

    more = panel.open_more()
    returned_scene = panel.back()
    returned_root = panel.back()
    unchanged_root = panel.back()

    assert scene.page == "scene"
    assert more.page == "more"
    assert more.category_id == "think"
    assert all(option.slot is None for option in more.options)
    assert returned_scene.page == "scene"
    assert returned_root.page == "root"
    assert unchanged_root == returned_root
    assert panel.snapshot == returned_root


def test_preparing_actions_remain_capable_but_are_pending_and_unselectable() -> None:
    panel = coordinator()
    policy_blocked = EntryActionRef("translate_to_english", "short")
    panel.open(
        "panel-1",
        preparing=True,
        disabled={policy_blocked: "Provider unavailable"},
    )

    scene = panel.select_digit("4").snapshot
    blocked = next(option for option in scene.options if option.action == policy_blocked)
    available = next(option for option in scene.options if option.action != policy_blocked)

    assert blocked.enabled is False
    assert blocked.pending is False
    assert blocked.disabled_reason == "Provider unavailable"
    assert available.enabled is True
    assert available.pending is True
    assert panel.select_digit(str(available.slot)).action is None


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
        load_config_bundle().entry_panel,
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


def test_input_lifecycle_projection_survives_navigation_and_density_changes() -> None:
    panel = coordinator()
    preview = EntryInputSourcePreview("preparing")
    root = panel.open(
        "panel-1",
        preparing=True,
        source_preview=preview,
    )
    scene = panel.select_digit("5").snapshot
    more = panel.open_more()
    compact = panel.toggle_density()

    assert root.status == scene.status == more.status == compact.status == "preparing"
    assert compact.source_preview == preview


def test_input_completion_and_failure_are_truthful_projection_transitions() -> None:
    panel = coordinator()
    panel.open("panel-1", preparing=True)

    completed = panel.complete_input_preparation(
        EntryInputSourcePreview("selection_text", "captured")
    )
    failed = panel.show_error(
        "target unavailable",
        source_preview=EntryInputSourcePreview("failed", "target unavailable"),
    )

    assert completed.status == "idle"
    assert completed.message == ""
    assert completed.source_preview.kind == "selection_text"
    assert failed.status == "error"
    assert failed.message == "target unavailable"
    assert failed.source_preview.kind == "failed"


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
