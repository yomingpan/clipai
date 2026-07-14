from __future__ import annotations

from ClipAI.core.models import ModelSelectionState, ProviderOption, ProviderSelectionState
from ClipAI.ui.tray import STATUS_COLORS, TrayController, create_tray_image


class MenuItem:
    def __init__(self, text, action, **kwargs) -> None:
        if callable(action) and hasattr(action, "__code__") and action.__code__.co_argcount > 2:
            raise ValueError(action)
        self.text = text
        self.action = action
        self.checked = kwargs.get("checked")
        self.enabled = kwargs.get("enabled")


class Menu:
    SEPARATOR = object()

    def __init__(self, *items) -> None:
        self.items = items


class Pystray:
    Menu = Menu
    MenuItem = MenuItem


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


def test_tray_keeps_diagnostics_callback_separate_from_export_work() -> None:
    events: list[str] = []
    tray = TrayController(lambda: None, lambda: events.append("export"))
    assert tray._on_export_diagnostics is not None
    tray._on_export_diagnostics()
    assert events == ["export"]


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
