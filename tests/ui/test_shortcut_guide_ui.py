from importlib.resources import files

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.core.hotkeys import MODIFIER_KEYS
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog
from ClipAI.ui.shortcut_guide import _KEY_ROWS


def test_keyboard_map_contains_every_configured_trigger_key() -> None:
    bundle = load_config_bundle()
    items = ShortcutGuideCatalog(
        bundle.shortcuts,
        bundle.actions,
        modifier_mode=bundle.app.modifier_mode,
    ).items()
    displayed_tokens = {token for row in _KEY_ROWS for _label, token in row}
    trigger_tokens = {
        token
        for item in items
        for token in item.key_tokens
        if token not in MODIFIER_KEYS
    }

    assert trigger_tokens <= displayed_tokens


def test_clipai_window_icon_resource_exists() -> None:
    assert files("ClipAI.ui").joinpath("assets", "clipai.ico").is_file()
