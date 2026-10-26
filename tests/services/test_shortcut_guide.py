from ClipAI.core.commands import ShortcutAttemptRejected, ShortcutKeyStateChanged, ShortcutPressEnded, ShortcutPressInvoked, ShortcutPressStarted
from ClipAI.core.commands import ShortcutPressThresholdReached
from ClipAI.core.models import ActionDefinition, ActionFeedbackContract, FeedbackReason, ShortcutDefinition, ShortcutObservationSnapshot, ShortcutPressId, ShortcutPressRef
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator


def test_captured_practice_press_quarantines_threshold_until_release_even_after_guide_closes():
    coordinator = ShortcutGuideCoordinator()
    press = ShortcutPressId(900)
    coordinator.open("practice", ())
    coordinator.handle(ShortcutPressStarted(press, "inline_dictation"))
    assert coordinator.handle(ShortcutPressThresholdReached(press, "inline_dictation")).consumed
    coordinator.close()
    assert coordinator.handle(ShortcutPressThresholdReached(press, "inline_dictation")).consumed
    coordinator.handle(ShortcutPressEnded(press, "inline_dictation", "released"))
    assert not coordinator.handle(ShortcutPressThresholdReached(press, "inline_dictation")).consumed


def guide_catalog() -> ShortcutGuideCatalog:
    feedback = ActionFeedbackContract(
        "協助使用者理解英文",
        "不取代使用者自己的理解",
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


def test_inline_guide_explains_release_gesture_and_altgr_migration():
    bundle = load_config_bundle()
    item = next(item for item in ShortcutGuideCatalog(bundle.shortcuts, bundle.actions, modifier_mode=bundle.app.modifier_mode).items() if item.shortcut_id == "inline_dictation")
    assert item.display_hotkey == "Right Alt"
    assert item.short_description.splitlines()[0] == "單獨按一下開始；再按一次收尾：短按直接貼上，長按潤飾後貼上。"
    assert "AltGr" in item.short_description
    assert "chord" in item.short_description
    assert "config/shortcuts.yaml" in item.short_description
    assert "Ctrl+Alt+M" in item.short_description


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

    assert len(items) == 34
    assert [item.shortcut_id for item in items] == [definition.id for definition in bundle.shortcuts.definitions()]
    assert {item.shortcut_id for item in items if item.long_title} == {
        "translate_to_english",
        "english_companion",
        "reading_friction",
        "expression_retrieval",
        "speak_selection_or_clipboard",
        "shorten_content",
        "extract_screenshot_text",
    }
    question = next(item for item in items if item.shortcut_id == "contextual_question")
    assert question.title == "問這段"
    assert question.display_hotkey == "Ctrl + Alt + R"


def test_guide_tracks_progress_and_verifies_short_press_for_this_open_only() -> None:
    coordinator = ShortcutGuideCoordinator()
    snapshot = coordinator.open("guide-1", guide_catalog().items())
    press_id = ShortcutPressId(7)

    assert snapshot.selected_shortcut_id == "english"
    progress = coordinator.handle(ShortcutKeyStateChanged(frozenset({"ctrl"})))
    assert progress.snapshot is not None
    assert progress.snapshot.phase == "keys_pressed"
    assert "Alt" in progress.snapshot.status_text

    coordinator.handle(ShortcutPressStarted(press_id, "english"))
    coordinator.handle(ShortcutKeyStateChanged(frozenset({"ctrl", "alt", "8"})))
    decision = coordinator.handle(ShortcutPressInvoked(press_id, "english", "short"))
    assert decision.consumed is True
    assert decision.snapshot is not None
    assert decision.snapshot.verified == frozenset({("english", "short")})
    assert "已驗證" in decision.snapshot.status_text

    coordinator.handle(ShortcutPressEnded(press_id, "english", "released"))
    final = coordinator.handle(ShortcutKeyStateChanged(frozenset()))
    assert final.snapshot is not None
    assert final.snapshot.phase == "listening"
    assert final.snapshot.pressed_keys == frozenset()

    coordinator.close("guide-1")
    reopened = coordinator.open("guide-2", guide_catalog().items())
    assert reopened.verified == frozenset()


def test_guide_consumes_rejected_attempt_while_open() -> None:
    coordinator = ShortcutGuideCoordinator()
    coordinator.open("guide-1", guide_catalog().items())

    invalid = coordinator.handle(ShortcutAttemptRejected())

    assert invalid.consumed is True
    assert invalid.snapshot is not None
    assert invalid.snapshot.phase == "invalid"


def test_captured_press_remains_quarantined_after_guide_closes_until_terminal_fact() -> None:
    coordinator = ShortcutGuideCoordinator()
    coordinator.open("guide-1", guide_catalog().items())
    press_id = ShortcutPressId(9)
    coordinator.handle(ShortcutPressStarted(press_id, "english"))
    coordinator.close("guide-1")

    assert coordinator.handle(ShortcutPressInvoked(press_id, "english", "short")).consumed is True
    assert coordinator.handle(ShortcutPressEnded(press_id, "english", "released")).consumed is True
    assert coordinator.handle(ShortcutPressInvoked(press_id, "english", "short")).consumed is False


def test_opening_guide_quarantines_press_active_in_observation_snapshot() -> None:
    coordinator = ShortcutGuideCoordinator()
    press_id = ShortcutPressId(4)
    coordinator.open(
        "guide-1",
        guide_catalog().items(),
        ShortcutObservationSnapshot(
            frozenset({"ctrl", "alt", "8"}),
            (ShortcutPressRef(press_id, "english"),),
        ),
    )
    coordinator.close("guide-1")

    assert coordinator.handle(ShortcutPressInvoked(press_id, "english", "long")).consumed is True
from ClipAI.app.config_loader import load_config_bundle
