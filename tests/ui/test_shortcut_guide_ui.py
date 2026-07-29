from importlib.resources import files

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.core.hotkeys import MODIFIER_KEYS
from ClipAI.core.models import ShortcutGuideItem, ShortcutGuideSnapshot
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog
from ClipAI.ui import shortcut_guide
from ClipAI.ui.shortcut_guide import ShortcutGuideDialog, _KEY_ROWS


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


def test_selection_update_reuses_existing_shortcut_buttons(monkeypatch) -> None:
    class Button:
        def __init__(self, _parent=None, **kwargs) -> None:
            self.config = kwargs
            self.destroyed = False

        def grid(self, **_kwargs) -> None:
            pass

        def configure(self, **kwargs) -> None:
            self.config.update(kwargs)

        def destroy(self) -> None:
            self.destroyed = True

    monkeypatch.setattr(shortcut_guide.ctk, "CTkButton", Button)
    dialog = ShortcutGuideDialog.__new__(ShortcutGuideDialog)
    dialog._shortcut_list = object()
    dialog._command_sink = lambda _command: None
    dialog._list_buttons = {}
    dialog._list_signature = ()
    items = (
        ShortcutGuideItem("one", "ctrl+alt+1", "Ctrl + Alt + 1", frozenset({"ctrl", "alt", "1"}), "One", "First"),
        ShortcutGuideItem("two", "ctrl+alt+2", "Ctrl + Alt + 2", frozenset({"ctrl", "alt", "2"}), "Two", "Second"),
    )

    dialog._rebuild_list(ShortcutGuideSnapshot("guide", items, "one"))
    original_buttons = dict(dialog._list_buttons)
    dialog._rebuild_list(ShortcutGuideSnapshot("guide", items, "two"))

    assert dialog._list_buttons == original_buttons
    assert all(button.destroyed is False for button in original_buttons.values())


def test_snapshot_update_does_not_raise_the_window() -> None:
    class Configurable:
        def configure(self, **_kwargs) -> None:
            pass

    class Window:
        def __init__(self) -> None:
            self.deiconify_calls = 0
            self.lift_calls = 0

        def deiconify(self) -> None:
            self.deiconify_calls += 1

        def lift(self) -> None:
            self.lift_calls += 1

    item = ShortcutGuideItem(
        "one",
        "ctrl+alt+1",
        "Ctrl + Alt + 1",
        frozenset({"ctrl", "alt", "1"}),
        "One",
        "First",
    )
    snapshot = ShortcutGuideSnapshot("guide", (item,), "one")
    dialog = ShortcutGuideDialog.__new__(ShortcutGuideDialog)
    dialog._window = Window()
    dialog._instruction = Configurable()
    dialog._status = Configurable()
    dialog._rebuild_list = lambda _snapshot: None
    dialog._apply_keyboard = lambda _item, _pressed_keys: None
    dialog._apply_detail = lambda _item: None

    dialog.apply(snapshot)

    assert dialog._window.deiconify_calls == 0
    assert dialog._window.lift_calls == 0

    dialog.show(snapshot)

    assert dialog._window.deiconify_calls == 1
    assert dialog._window.lift_calls == 1
