from ClipAI.core.commands import ShortcutGestureProgressed, ShortcutTriggered
from ClipAI.core.models import ActionDefinition, ActionFeedbackContract, FeedbackReason, ShortcutDefinition
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator


def guide_catalog() -> ShortcutGuideCatalog:
    feedback = ActionFeedbackContract(
        "協助使用者理解英文",
        "保留自己的理解",
        "是否真正理解？",
        (FeedbackReason("other", "其他"),),
    )
    actions = ActionCatalog([
        ActionDefinition(
            "english",
            "English Companion",
            "system",
            "{input}",
            {},
            feedback_contract=feedback,
        ),
    ])
    shortcuts = ShortcutCatalog([
        ShortcutDefinition("english", "ctrl+alt+8", "start_action", "english"),
        ShortcutDefinition("speech", "ctrl+alt+q", "speak_selection_or_clipboard"),
    ])
    return ShortcutGuideCatalog(shortcuts, actions, modifier_mode="ctrl_alt")


def test_catalog_projects_action_and_speech_semantics_in_shortcut_order() -> None:
    english, speech = guide_catalog().items()

    assert english.display_hotkey == "Ctrl + Alt + 8"
    assert english.title == "English Companion"
    assert english.short_description == "協助使用者理解英文"
    assert english.long_title == ""
    assert speech.title == "朗讀選取文字或剪貼簿"
    assert speech.long_title == "語音快捷鍵組合"


def test_catalog_displays_the_effective_modifier_mode() -> None:
    catalog = guide_catalog()
    catalog._modifier_mode = "alt_shift"

    assert catalog.items()[0].display_hotkey == "Alt + Shift + 8"


def test_real_config_projects_every_shortcut_and_declared_long_variant() -> None:
    bundle = load_config_bundle()
    items = ShortcutGuideCatalog(
        bundle.shortcuts,
        bundle.actions,
        modifier_mode=bundle.app.modifier_mode,
    ).items()

    assert len(items) == 20
    assert [item.shortcut_id for item in items] == [definition.id for definition in bundle.shortcuts.definitions()]
    assert {item.shortcut_id for item in items if item.long_title} == {
        "translate_to_english",
        "english_companion",
        "speak_selection_or_clipboard",
        "shorten_content",
        "extract_screenshot_text",
    }


def test_guide_tracks_progress_and_verifies_short_press_for_this_open_only() -> None:
    coordinator = ShortcutGuideCoordinator()
    snapshot = coordinator.open("guide-1", guide_catalog().items())

    assert snapshot.selected_shortcut_id == "english"
    progress = coordinator.observe(ShortcutGestureProgressed(7, frozenset({"ctrl"})))
    assert progress is not None
    assert progress.phase == "keys_pressed"
    assert "Alt" in progress.status_text

    coordinator.observe(ShortcutGestureProgressed(7, frozenset({"ctrl", "alt", "8"})))
    decision = coordinator.consume(ShortcutTriggered("english", "short", 7))
    assert decision.consumed is True
    assert decision.snapshot is not None
    assert decision.snapshot.verified == frozenset({("english", "short")})
    assert "已驗證" in decision.snapshot.status_text

    final = coordinator.observe(ShortcutGestureProgressed(7, frozenset(), ended=True))
    assert final is not None
    assert final.phase == "recognized"
    assert final.pressed_keys == frozenset()

    coordinator.close("guide-1")
    reopened = coordinator.open("guide-2", guide_catalog().items())
    assert reopened.verified == frozenset()


def test_guide_consumes_invalid_and_long_release_without_side_effect_decisions() -> None:
    coordinator = ShortcutGuideCoordinator()
    coordinator.open("guide-1", guide_catalog().items())

    invalid = coordinator.consume(ShortcutTriggered("", "invalid", 3))
    release = coordinator.consume(ShortcutTriggered("english", "long_release", 3))

    assert invalid.consumed is True
    assert invalid.snapshot is not None
    assert invalid.snapshot.phase == "invalid"
    assert release.consumed is True


def test_captured_gesture_remains_quarantined_after_guide_closes() -> None:
    coordinator = ShortcutGuideCoordinator()
    coordinator.open("guide-1", guide_catalog().items())
    coordinator.observe(ShortcutGestureProgressed(9, frozenset({"ctrl", "alt", "8"})))
    coordinator.close("guide-1")

    assert coordinator.wants_progress(9) is True
    assert coordinator.wants_progress(10) is False
    assert coordinator.consume(ShortcutTriggered("english", "short", 9)).consumed is True
    coordinator.observe(ShortcutGestureProgressed(9, frozenset(), ended=True))
    assert coordinator.consume(ShortcutTriggered("english", "short", 9)).consumed is False


def test_cancel_closes_guide_and_keeps_trigger_consumed() -> None:
    coordinator = ShortcutGuideCoordinator()
    coordinator.open("guide-1", guide_catalog().items())

    decision = coordinator.consume(ShortcutTriggered("", "cancel", 4))

    assert decision.consumed is True
    assert decision.close_requested is True
    assert coordinator.snapshot is None
from ClipAI.app.config_loader import load_config_bundle
