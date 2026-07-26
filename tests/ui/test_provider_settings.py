from ClipAI.ui.provider_settings import _credential_status
from importlib.resources import files


def test_provider_settings_ships_the_clipai_windows_icon() -> None:
    icon = files("ClipAI.ui").joinpath("assets", "clipai.ico")
    assert icon.is_file()


def test_credential_status_exposes_only_safe_hint() -> None:
    assert _credential_status("••••A7kP") == "Using saved API key ending in A7kP. Leave blank to keep it."
    assert _credential_status("configured") == "API key is configured. Leave blank to keep it."
    assert _credential_status("", optional=True) == "API key is optional. No saved key is configured."
