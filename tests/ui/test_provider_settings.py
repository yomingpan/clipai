from ClipAI.ui.provider_settings import ProviderSettingsDialog, _credential_status
from importlib.resources import files
from types import SimpleNamespace
import pytest


def test_provider_settings_ships_the_clipai_windows_icon() -> None:
    icon = files("ClipAI.ui").joinpath("assets", "clipai.ico")
    assert icon.is_file()


def test_credential_status_exposes_only_safe_hint() -> None:
    assert _credential_status("••••A7kP") == "Using saved API key ending in A7kP. Leave blank to keep it."
    assert _credential_status("configured") == "API key is configured. Leave blank to keep it."
    assert _credential_status("", optional=True) == "API key is optional. No saved key is configured."


def test_escape_defers_provider_settings_to_the_global_gesture_owner() -> None:
    events = []
    dialog = ProviderSettingsDialog.__new__(ProviderSettingsDialog)
    dialog.close = lambda: events.append("close")

    assert dialog._handle_escape() == "break"
    assert events == []


def test_model_refresh_carries_new_key_for_a_standard_provider() -> None:
    events = []
    dialog = ProviderSettingsDialog.__new__(ProviderSettingsDialog)
    dialog._state = SimpleNamespace(operation_state="idle")
    dialog._provider = SimpleNamespace(get=lambda: "gemini")
    dialog._api_key = SimpleNamespace(get=lambda: "new-valid-key")
    dialog._option = lambda _: SimpleNamespace(capabilities=SimpleNamespace(custom_endpoint=False))
    dialog._selected_model = lambda _: "gemini-2.5-flash"
    dialog._command_sink = events.append
    dialog._refresh_models()
    assert events[0].connection is not None
    assert events[0].connection.api_key == "new-valid-key"


@pytest.mark.parametrize("operation_kind,cleared", [("refresh", False), ("save", True)])
def test_only_successful_save_clears_the_entered_key(operation_kind, cleared) -> None:
    deleted = []
    widget = SimpleNamespace(configure=lambda **_: None)
    dialog = ProviderSettingsDialog.__new__(ProviderSettingsDialog)
    for name in ("_provider_menu", "_model_menu", "_gateway_name", "_gateway_url",
                 "_model_entry", "_save", "_refresh", "_message"):
        setattr(dialog, name, widget)
    dialog._api_key = SimpleNamespace(configure=lambda **_: None,
                                     delete=lambda *_: deleted.append(True), focus_set=lambda: None)
    dialog._provider = SimpleNamespace(set=lambda _: None)
    dialog._gateway_custom_mode = SimpleNamespace(set=lambda _: None)
    dialog._gateway_model_mode_changed = lambda: None
    dialog._window = SimpleNamespace(deiconify=lambda: None, lift=lambda: None)
    dialog._loaded_provider = "gemini"
    dialog._apply_provider = lambda *_, **__: None
    dialog._option = lambda _: None
    state = SimpleNamespace(providers=(), selected_provider="gemini", selected_model="model",
                            operation_state="succeeded", operation_kind=operation_kind, message="")
    dialog.apply(state)
    assert bool(deleted) is cleared
