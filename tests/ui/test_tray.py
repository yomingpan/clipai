from __future__ import annotations

import sys

from ClipAI.core.models import GuidancePreferences, ModelSelectionState, ProviderOption, ProviderSelectionState, SpeechSpeedState
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceProjection
from ClipAI.ui.tray import SHORTCUT_GUIDE_MENU_LABEL, STATUS_COLORS, TrayController, create_tray_image


class MenuItem:
    def __init__(self, text, action, **kwargs) -> None:
        if callable(action) and hasattr(action, "__code__") and action.__code__.co_argcount > 2:
            raise ValueError(action)
        self.text = text
        self.action = action
        self.checked = kwargs.get("checked")
        self.enabled = kwargs.get("enabled")
        self.radio = kwargs.get("radio", False)


class Menu:
    SEPARATOR = object()

    def __init__(self, *items) -> None:
        self.items = items


class Pystray:
    Menu = Menu
    MenuItem = MenuItem

    class Icon:
        def __init__(self, name, icon, title, *, menu) -> None:
            self.name = name
            self.icon = icon
            self.title = title
            self.menu = menu
            self.menu_updates = 0

        def run(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update_menu(self) -> None:
            self.menu_updates += 1


class NotificationIcon:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, str]] = []

    def notify(self, message: str, title: str) -> None:
        self.notifications.append((message, title))


def test_tray_image_uses_requested_size_and_status_palette() -> None:
    image = create_tray_image("processing", size=32)
    assert image.size == (32, 32)
    assert STATUS_COLORS["processing"] == (255, 140, 0)


def test_tray_memory_indicator_changes_rendered_pixels() -> None:
    idle = create_tray_image("idle", memory_active=False)
    memory = create_tray_image("idle", memory_active=True)
    assert idle.tobytes() != memory.tobytes()


def test_tray_status_is_a_dumb_projection_without_reset_timer() -> None:
    tray = TrayController(lambda: None)
    tray.set_status("success")
    assert tray._status == "success"
    tray.stop()


def test_tray_projects_status_and_current_configuration_as_compact_summaries() -> None:
    tray = TrayController(
        lambda: None,
        model_selection=ModelSelectionState("openai", ("gpt-test",), "gpt-test"),
        provider_selection=ProviderSelectionState((ProviderOption("openai", "OpenAI", ("gpt-test",), "gpt-test", True),), "openai"),
    )
    assert tray._configuration_summary() == "OpenAI · gpt-test"
    tray.set_status("error")
    assert tray._status == "error"
    assert tray._tooltip() == "ClipAI vdevelopment — Needs attention · OpenAI · gpt-test"


def test_tray_top_menu_and_tooltip_show_the_application_version() -> None:
    tray = TrayController(lambda: None, application_version="3.6.5")

    assert tray._application_label() == "ClipAI v3.6.5 — Ready"
    assert tray._tooltip() == "ClipAI v3.6.5 — Ready · No provider configured"

    tray.stop()


def test_tray_notification_uses_the_existing_icon() -> None:
    tray = TrayController(lambda: None)
    icon = NotificationIcon()
    tray._icon = icon

    tray.notify("ClipAI", "Configuration saved")

    assert icon.notifications == [("Configuration saved", "ClipAI")]


def test_tray_keeps_diagnostics_callback_separate_from_export_work() -> None:
    events: list[str] = []
    tray = TrayController(lambda: None, lambda: events.append("export"))
    assert tray._on_export_diagnostics is not None
    tray._on_export_diagnostics()
    assert events == ["export"]


def test_tray_exposes_english_keyboard_shortcut_entry_callback() -> None:
    events = []
    tray = TrayController(lambda: None, on_open_shortcut_guide=lambda: events.append("open"))

    assert SHORTCUT_GUIDE_MENU_LABEL == "Keyboard Shortcuts..."
    assert tray._on_open_shortcut_guide is not None
    tray._on_open_shortcut_guide()
    assert events == ["open"]


def test_tray_model_menu_projects_only_available_models_and_checks_active() -> None:
    tray = TrayController(
        lambda: None,
        model_selection=ModelSelectionState("openai", ("small", "large"), "small"),
        on_select_model=lambda _provider, _model: None,
    )
    root = tray._build_model_menu(Pystray)
    assert root.text == "Model: small"
    assert [item.text for item in root.action.items] == ["small", "large"]
    assert root.action.items[0].checked(None) is True
    assert root.action.items[1].checked(None) is False
    assert all(item.action.__code__.co_argcount == 2 for item in root.action.items)


def test_tray_model_click_enters_pending_and_emits_typed_values_once() -> None:
    events: list[tuple[str, str]] = []
    tray = TrayController(
        lambda: None,
        model_selection=ModelSelectionState("openai", ("small", "large"), "small"),
        on_select_model=lambda provider, model: events.append((provider, model)),
    )
    root = tray._build_model_menu(Pystray)
    root.action.items[1].action(None, None)
    root.action.items[0].action(None, None)
    pending = tray._build_model_menu(Pystray)
    assert events == [("openai", "large")]
    assert pending.text == "Model (large)..."
    assert all(item.enabled(None) is False for item in pending.action.items)


def test_tray_accepts_authoritative_model_projection_after_pending() -> None:
    tray = TrayController(
        lambda: None,
        model_selection=ModelSelectionState("openai", ("small", "large"), "small", "large"),
        on_select_model=lambda _provider, _model: None,
    )
    tray.set_model_selection(ModelSelectionState("openai", ("small", "large"), "large"))
    root = tray._build_model_menu(Pystray)
    assert root.text == "Model: large"
    assert root.action.items[1].checked(None) is True


def test_tray_provider_menu_projects_options_and_emits_selection() -> None:
    events: list[str] = []
    selection = ProviderSelectionState(
        (
            ProviderOption("openai", "OpenAI", ("small",), "small", True),
            ProviderOption("gemini", "Gemini", ("flash",), "flash", True),
        ),
        "openai",
    )
    tray = TrayController(
        lambda: None,
        provider_selection=selection,
        on_select_provider=events.append,
    )
    root = tray._build_provider_menu(Pystray)
    assert root.text == "Provider: openai"
    assert [item.text for item in root.action.items] == ["OpenAI", "Gemini"]
    root.action.items[1].action(None, None)
    assert events == ["gemini"]
    assert tray._build_provider_menu(Pystray).text == "Provider (gemini)..."


def test_tray_marks_custom_current_model_and_disables_during_refresh() -> None:
    tray = TrayController(
        lambda: None,
        model_selection=ModelSelectionState("openai", ("custom-model",), "custom-model", refreshing=True, custom_models=("custom-model",)),
        on_select_model=lambda _provider, _model: None,
    )
    root = tray._build_model_menu(Pystray)
    assert root.text == "Model (refreshing)..."
    assert root.action.items[0].text == "custom-model (custom/current)"
    assert root.action.items[0].enabled(None) is False


def test_tray_disables_provider_and_model_mutations_during_configuration_operation() -> None:
    events = []
    providers = (
        ProviderOption("openai", "OpenAI", ("small", "large"), "small", True),
        ProviderOption("gemini", "Gemini", ("flash",), "flash", True),
    )
    tray = TrayController(
        lambda: None,
        model_selection=ModelSelectionState("openai", ("small", "large"), "small", configuration_pending=True),
        provider_selection=ProviderSelectionState(providers, "openai", configuration_pending=True),
        on_select_model=lambda provider, model: events.append((provider, model)),
        on_select_provider=lambda provider: events.append(provider),
    )

    model_menu = tray._build_model_menu(Pystray)
    provider_menu = tray._build_provider_menu(Pystray)
    model_menu.action.items[1].action(None, None)
    provider_menu.action.items[1].action(None, None)

    assert model_menu.text == "Model (updating)..."
    assert provider_menu.text == "Provider (updating)..."
    assert all(item.enabled(None) is False for item in model_menu.action.items)
    assert all(item.enabled(None) is False for item in provider_menu.action.items)
    assert events == []


def test_guidance_menu_emits_intents_without_optimistically_changing_checked_state() -> None:
    events = []
    tray = TrayController(
        lambda: None,
        guidance_preferences=GuidancePreferences(True, frozenset({"shorten"})),
        on_set_first_use_hints=lambda enabled: events.append(("set", enabled)),
        on_reset_first_use_hints=lambda: events.append(("reset",)),
    )
    menu = tray._build_guidance_menu(Pystray)
    toggle, reset = menu.action.items

    assert menu.text == "Usage Guidance"
    assert toggle.text == "Show tips the first time each Recipe is used"
    assert reset.text == "Show All Tips Again"

    toggle.action(None, None)
    reset.action(None, None)

    assert events == [("set", False), ("reset",)]
    assert toggle.checked(None) is True


def test_guidance_menu_reflects_only_authoritative_saved_projection() -> None:
    tray = TrayController(
        lambda: None,
        guidance_preferences=GuidancePreferences(True),
        on_set_first_use_hints=lambda _enabled: None,
        on_reset_first_use_hints=lambda: None,
    )
    pending = GuidancePreferences(True, update_pending=True)
    tray.set_guidance_preferences(pending)
    toggle, reset = tray._build_guidance_menu(Pystray).action.items
    assert toggle.checked(None) is True
    assert toggle.enabled(None) is False
    assert reset.enabled(None) is False

    tray.set_guidance_preferences(GuidancePreferences(False))
    toggle = tray._build_guidance_menu(Pystray).action.items[0]
    assert toggle.checked(None) is False
    assert toggle.enabled(None) is True


def test_speech_speed_menu_lists_four_presets_and_emits_without_optimistic_selection() -> None:
    events = []
    tray = TrayController(
        lambda: None,
        speech_speed=SpeechSpeedState("normal"),
        on_set_speech_speed=events.append,
    )

    menu = tray._build_speech_speed_menu(Pystray)
    items = menu.action.items

    assert menu.text(None) == "Speech Speed"
    assert [item.text for item in items] == ["Slow", "Normal", "Fast", "Super Fast"]
    assert [item.checked(None) for item in items] == [False, True, False, False]
    assert all(item.radio is True for item in items)
    assert items[1].enabled(None) is False

    items[2].action(None, None)
    assert events == ["fast"]
    assert items[1].checked(None) is True


def test_speech_speed_menu_projects_saving_without_changing_authoritative_check() -> None:
    tray = TrayController(
        lambda: None,
        speech_speed=SpeechSpeedState("normal", "fast", update_pending=True),
        on_set_speech_speed=lambda _speed: None,
    )

    menu = tray._build_speech_speed_menu(Pystray)

    assert menu.text(None) == "Speech Speed (saving...)"
    assert [item.checked(None) for item in menu.action.items] == [False, True, False, False]
    assert all(item.enabled(None) is False for item in menu.action.items)


def test_speech_speed_menu_distinguishes_custom_and_unavailable_states() -> None:
    tray = TrayController(
        lambda: None,
        speech_speed=SpeechSpeedState(None),
        on_set_speech_speed=lambda _speed: None,
    )
    assert tray._build_speech_speed_menu(Pystray).text(None) == "Speech Speed (Custom)"

    tray.set_speech_speed(SpeechSpeedState("normal", available=False))
    menu = tray._build_speech_speed_menu(Pystray)
    assert menu.text(None) == "Speech Speed (unavailable)"
    assert all(item.enabled(None) is False for item in menu.action.items)


def test_speech_speed_follows_keyboard_shortcuts_and_is_separated_from_guidance(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pystray", Pystray)
    tray = TrayController(
        lambda: None,
        on_open_provider_settings=lambda: None,
        on_open_shortcut_guide=lambda: None,
        speech_speed=SpeechSpeedState("normal"),
        on_set_speech_speed=lambda _speed: None,
        guidance_preferences=GuidancePreferences(),
        on_set_first_use_hints=lambda _enabled: None,
        on_reset_first_use_hints=lambda: None,
    )

    tray.start()
    tray._thread.join(timeout=1)
    assert tray._icon.menu.items[0].text(None) == "ClipAI vdevelopment — Ready"
    items = tray._icon.menu.items
    shortcut_index = next(index for index, item in enumerate(items) if getattr(item, "text", None) == "Keyboard Shortcuts...")
    speech_index = next(index for index, item in enumerate(items) if callable(getattr(item, "text", None)) and item.text(None) == "Speech Speed")
    guidance_index = next(index for index, item in enumerate(items) if getattr(item, "text", None) == "Usage Guidance")

    assert speech_index == shortcut_index + 1
    assert items[speech_index + 1] is Menu.SEPARATOR
    assert guidance_index == speech_index + 2


def test_voice_menu_projects_authoritative_state_without_optimistic_toggle() -> None:
    events = []
    tray = TrayController(
        lambda: None,
        voice=VoiceProjection(VoiceCapabilityPhase.SETUP_REQUIRED, "zh-TW"),
        on_enable_voice=lambda: events.append("enable"),
        on_disable_voice=lambda: events.append("disable"),
        on_manage_voice_permission=lambda: events.append("manage"),
    )
    menu = tray._build_voice_menu(Pystray)
    assert menu.text(None) == "Voice Input (setup required)"
    enable, disable, manage = menu.action.items
    assert enable.enabled(None) is True
    assert disable.enabled(None) is False
    assert manage.enabled(None) is False
    enable.action(None, None)
    assert events == ["enable"]


def test_existing_voice_menu_reprojects_enable_and_disable_after_authoritative_update(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pystray", Pystray)
    events: list[str] = []
    tray = TrayController(
        lambda: None,
        voice=VoiceProjection(VoiceCapabilityPhase.SETUP_REQUIRED, "zh-TW"),
        on_enable_voice=lambda: events.append("enable"),
        on_disable_voice=lambda: events.append("disable"),
    )
    tray.start()
    tray._thread.join(timeout=1)
    menu = next(
        item
        for item in tray._icon.menu.items
        if callable(getattr(item, "text", None)) and item.text(None).startswith("Voice Input")
    )
    enable, disable = menu.action.items

    tray.set_voice_projection(VoiceProjection(VoiceCapabilityPhase.READY, "zh-TW"))

    assert tray._icon.menu_updates == 1
    assert menu.text(None) == "Voice Input (ready)"
    assert enable.enabled(None) is False
    assert disable.enabled(None) is True
    disable.action(None, None)

    tray.set_voice_projection(VoiceProjection(VoiceCapabilityPhase.DISABLED, "zh-TW"))

    assert tray._icon.menu_updates == 2
    assert menu.text(None) == "Voice Input (disabled)"
    assert enable.enabled(None) is True
    assert disable.enabled(None) is False
    enable.action(None, None)
    assert events == ["disable", "enable"]


def test_voice_menu_exposes_permission_repair_when_microphone_is_blocked() -> None:
    events = []
    tray = TrayController(
        lambda: None,
        voice=VoiceProjection(VoiceCapabilityPhase.PERMISSION_BLOCKED, "zh-TW"),
        on_enable_voice=lambda: None,
        on_disable_voice=lambda: None,
        on_manage_voice_permission=lambda: events.append("manage"),
    )

    menu = tray._build_voice_menu(Pystray)
    manage = menu.action.items[-1]
    assert manage.text == "Manage Microphone Permission"
    assert manage.enabled(None) is True
    manage.action(None, None)
    assert events == ["manage"]
