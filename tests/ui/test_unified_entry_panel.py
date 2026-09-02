import tkinter as tk

import customtkinter as ctk
import pytest

from ClipAI.core.commands import (
    CloseEntryPanel,
    EntryPanelActionSelected,
    EntryPanelBack,
    EntryPanelSlotSelected,
    EntryPanelToggleDensity,
    RetryEntryPanelInput,
)
from ClipAI.core.models import DisplayMetrics, EntryActionRef, EntryInputSourcePreview, EntryPanelOption, EntryPanelSnapshot, PopupBounds
from ClipAI.ui.base_dialog import ACTION_HOVER_COLOR
from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceSpec
from ClipAI.ui.unified_entry_panel import EntryPanelIntentAdapter, UnifiedEntryPanelDialog, _body_render_key, _source_preview_text


@pytest.mark.integration
def test_panel_dialog_builds_and_closes_cleanly() -> None:
    """A native Panel surface must not leave a partial Toplevel on startup."""

    class NativeSurface:
        def activate(self, _window_id: int) -> bool:
            return True

        def hide_from_task_switcher(self, _window_id: int) -> None:
            pass

    class MetricsReader:
        def current(self):
            return DisplayMetrics(1.0, 0, 0, 1920, 1080, 420, 320)

    master = ctk.CTk()
    master.withdraw()
    dialog = None
    host = None
    try:
        host = PrimarySurfaceHost(
            master,
            PrimarySurfaceSpec(PopupBounds(268, 220, 400, 320)),
            NativeSurface(),
        )
        lease = host.acquire()
        dialog = UnifiedEntryPanelDialog(
            master,
            lambda _command: None,
            NativeSurface(),
            MetricsReader(),
            primary_surface_host=host,
            primary_surface_lease=lease,
        )
        snapshot = EntryPanelSnapshot(
            "panel-1",
            "scene",
            options=(
                EntryPanelOption(
                    1,
                    "測試 Action",
                    action=EntryActionRef("shorten_content", "short"),
                ),
            ),
        )
        dialog.apply(snapshot)
        assert host.mount(lease, dialog) is True
        assert host.show(lease) is True
        dialog.reveal()
        header = dialog._shell.winfo_children()[0]
        title_label = next(
            child
            for child in header.winfo_children()
            if isinstance(child, ctk.CTkLabel) and child.cget("text") == "ClipAI"
        )
        master.update()

        for handle in (header._canvas, title_label._canvas):
            before = (dialog._window.winfo_x(), dialog._window.winfo_y())
            handle.event_generate("<ButtonPress-1>", x=5, y=5)
            handle.event_generate("<B1-Motion>", x=35, y=25)
            master.update()
            assert (dialog._window.winfo_x(), dialog._window.winfo_y()) == (
                before[0] + 30,
                before[1] + 20,
            )
        card = dialog._option_buttons[0]
        title = next(child for child in card.winfo_children() if child.cget("text"))

        assert title.cget("text") == "1  測試 Action"
        card._canvas.event_generate("<Enter>")
        master.update_idletasks()
        assert card.cget("fg_color") == "#303030"
        assert card.cget("border_color") == ACTION_HOVER_COLOR

        root_snapshot = EntryPanelSnapshot(
            "panel-1",
            "root",
            density="detailed",
            options=(
                *(EntryPanelOption(
                    slot,
                    f"最近 {slot}",
                    action=EntryActionRef("shorten_content", "short"),
                ) for slot in range(3)),
                *(EntryPanelOption(
                    slot,
                    f"情境 {slot}",
                    category_id=f"category-{slot}",
                ) for slot in range(3, 7)),
            ),
        )
        dialog.show(root_snapshot)
        master.update_idletasks()
        divider = next(
            child
            for child in dialog._body.winfo_children()
            if child.cget("corner_radius") == 0 and child.winfo_height() <= 3
        )

        assert dialog._density.get() == 1
        assert divider.winfo_height() >= 2
        assert all(card.winfo_height() >= 48 for card in dialog._option_buttons)
    finally:
        if host is not None:
            host.close()
        try:
            master.destroy()
        except tk.TclError:
            pass


def test_intent_adapter_emits_typed_mouse_and_keyboard_commands() -> None:
    commands = []
    adapter = EntryPanelIntentAdapter(commands.append)
    action = EntryActionRef("shorten_content", "short")
    snapshot = EntryPanelSnapshot(
        "panel-1",
        "scene",
        options=(EntryPanelOption(1, "縮短內容", action=action),),
    )
    adapter.apply(snapshot)

    adapter.select(snapshot.options[0])
    adapter.select_slot(2)
    adapter.toggle_density()
    adapter.retry_input()
    adapter.back()
    adapter.close()

    assert commands == [
        EntryPanelActionSelected("panel-1", action),
        EntryPanelSlotSelected("panel-1", 2),
        EntryPanelToggleDensity("panel-1"),
        RetryEntryPanelInput("panel-1"),
        EntryPanelBack("panel-1"),
        CloseEntryPanel("panel-1"),
    ]


@pytest.mark.parametrize(
    ("preview", "text"),
    [
        (EntryInputSourcePreview("preparing"), "正在讀取選取內容…"),
        (EntryInputSourcePreview("selection_text", "selected"), "選取文字：selected"),
        (EntryInputSourcePreview("clipboard_text", "copied"), "剪貼簿文字：copied"),
        (EntryInputSourcePreview("clipboard_image"), "剪貼簿截圖"),
        (EntryInputSourcePreview("workflow_selection", "chosen"), "Popup 選取文字：chosen"),
        (EntryInputSourcePreview("workflow_result", "result"), "目前結果：result"),
        (EntryInputSourcePreview("failed", "target changed"), "讀取失敗：target changed"),
    ],
)
def test_source_preview_has_stable_truthful_copy(preview, text) -> None:
    assert _source_preview_text(preview) == text


def test_intent_adapter_emits_one_action_selection_until_projection_changes() -> None:
    commands = []
    adapter = EntryPanelIntentAdapter(commands.append)
    option = EntryPanelOption(
        0,
        "最近使用",
        action=EntryActionRef("shorten_content", "short"),
    )
    snapshot = EntryPanelSnapshot("panel-1", "root", options=(option,))
    adapter.apply(snapshot)

    adapter.select(option)
    adapter.select(option)

    assert commands == [
        EntryPanelActionSelected("panel-1", option.action),
    ]


def test_disabled_option_does_not_emit_action_intent() -> None:
    commands = []
    adapter = EntryPanelIntentAdapter(commands.append)
    option = EntryPanelOption(
        1,
        "Unavailable",
        action=EntryActionRef("shorten_content", "short"),
        enabled=False,
        disabled_reason="Provider is busy",
    )
    adapter.apply(EntryPanelSnapshot("panel-1", "scene", options=(option,)))

    adapter.select(option)

    assert commands == []


def test_pending_option_does_not_emit_action_intent_even_while_enabled() -> None:
    commands = []
    adapter = EntryPanelIntentAdapter(commands.append)
    option = EntryPanelOption(
        1,
        "Preparing",
        action=EntryActionRef("shorten_content", "short"),
        enabled=True,
        pending=True,
    )
    adapter.apply(EntryPanelSnapshot("panel-1", "scene", options=(option,)))

    adapter.select(option)

    assert commands == []


def test_body_render_key_ignores_option_lifecycle_but_tracks_visible_detail() -> None:
    action = EntryActionRef("shorten_content", "short")
    baseline = EntryPanelSnapshot(
        "panel-1",
        "scene",
        options=(EntryPanelOption(1, "Shorten", "Description", action=action),),
    )
    lifecycle = EntryPanelSnapshot(
        "panel-1",
        "scene",
        options=(EntryPanelOption(
            1,
            "Shorten",
            "Description",
            action=action,
            enabled=False,
            pending=True,
            disabled_reason="Blocked",
        ),),
    )

    assert _body_render_key(baseline) == _body_render_key(lifecycle)
    assert _body_render_key(baseline) != _body_render_key(
        EntryPanelSnapshot(
            "panel-1",
            "scene",
            density="compact",
            options=baseline.options,
        )
    )


def test_option_card_callback_reads_latest_option_after_in_place_update(monkeypatch) -> None:
    class Widget:
        def __init__(self, _parent=None, **_kwargs) -> None:
            self.bindings = {}

        def grid_columnconfigure(self, *_args, **_kwargs) -> None:
            pass

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

        def configure(self, **_kwargs) -> None:
            pass

        def grid(self, **_kwargs) -> None:
            pass

        def grid_configure(self, **_kwargs) -> None:
            pass

        def grid_forget(self) -> None:
            pass

        def after_idle(self, callback) -> None:
            callback()

    selected = []
    monkeypatch.setattr("ClipAI.ui.unified_entry_panel.ctk.CTkFrame", Widget)
    monkeypatch.setattr("ClipAI.ui.unified_entry_panel.ctk.CTkLabel", Widget)
    monkeypatch.setattr("ClipAI.ui.unified_entry_panel.ctk.CTkFont", lambda **_kwargs: object())
    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._intent = type("Intent", (), {"select": lambda _self, option: selected.append(option)})()
    dialog._option_buttons = []
    dialog._option_updaters = []
    action = EntryActionRef("shorten_content", "short")
    initial = EntryPanelOption(1, "Shorten", action=action, enabled=False)
    latest = EntryPanelOption(1, "Shorten", action=action, enabled=True)

    card = dialog._create_option_card(
        object(),
        initial,
        EntryPanelSnapshot("panel-1", "scene"),
    )
    dialog._option_updaters[0](latest)
    card.bindings["<Button-1>"]()

    assert selected == [latest]


def test_projection_text_respects_density_and_keeps_disabled_reason() -> None:
    option = EntryPanelOption(
        1,
        "縮短內容",
        "保留意思並縮短篇幅",
        enabled=False,
        disabled_reason="AI 正在回答",
    )

    detailed = UnifiedEntryPanelDialog._option_text(
        option,
        EntryPanelSnapshot("panel-1", "scene", density="detailed"),
    )
    compact = UnifiedEntryPanelDialog._option_text(
        option,
        EntryPanelSnapshot("panel-1", "scene", density="compact"),
    )

    assert "保留意思並縮短篇幅" in detailed
    assert "保留意思並縮短篇幅" not in compact
    assert "AI 正在回答" in detailed
    assert "AI 正在回答" in compact


def test_show_never_changes_primary_host_geometry() -> None:
    class Host:
        def is_mounted(self, _lease) -> bool:
            return True

    class Lifecycle:
        def focus(self, _target: object) -> None:
            pass

    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._primary_surface_host = Host()
    dialog._primary_surface_lease = "lease"
    dialog._lifecycle = Lifecycle()
    dialog._snapshot = None
    dialog.apply = lambda snapshot: setattr(dialog, "_snapshot", snapshot)
    dialog._first_focus_target = lambda: None

    dialog.show(EntryPanelSnapshot("panel-1", "root"))
    dialog.show(EntryPanelSnapshot("panel-1", "root", density="compact"))


def test_show_does_not_rebuild_an_unchanged_projection() -> None:
    class Window:
        def geometry(self, _value: str) -> None:
            pass

        def update_idletasks(self) -> None:
            pass

        def winfo_id(self) -> int:
            return 42

        def deiconify(self) -> None:
            pass

    class NativeSurface:
        def hide_from_task_switcher(self, _window_id: int) -> None:
            pass

    class Lifecycle:
        def focus(self, _target: object) -> None:
            pass

    class Host:
        def is_mounted(self, _lease) -> bool:
            return True

    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._window = Window()
    dialog._native_window_surface = NativeSurface()
    dialog._display_metrics = object()
    dialog._lifecycle = Lifecycle()
    dialog._primary_surface_host = Host()
    dialog._primary_surface_lease = "lease"
    dialog._placed_panel_id = None
    dialog._snapshot = None
    applied = []

    def apply(snapshot) -> None:
        applied.append(snapshot)
        dialog._snapshot = snapshot

    dialog.apply = apply
    dialog._first_focus_target = lambda: None
    snapshot = EntryPanelSnapshot("panel-1", "root")

    dialog.show(snapshot, anchor=PopupBounds(120, 80, 400, 320))
    dialog.show(snapshot, anchor=PopupBounds(120, 80, 400, 320))

    assert applied == [snapshot]


def test_preparing_projection_keeps_existing_option_widgets_alive() -> None:
    class Intent:
        def apply(self, _snapshot) -> None:
            pass

    class EscapeButton:
        def configure(self, **_kwargs) -> None:
            pass

        def grid(self) -> None:
            pass

        def grid_remove(self) -> None:
            pass

    class DensitySwitch:
        def select(self) -> None:
            pass

        def deselect(self) -> None:
            pass

    class Tooltip:
        def set_text(self, _text: str) -> None:
            pass

    option = EntryPanelOption(
        1,
        "縮短內容",
        action=EntryActionRef("shorten_content", "short"),
    )
    idle = EntryPanelSnapshot("panel-1", "scene", options=(option,))
    preparing = EntryPanelSnapshot(
        "panel-1",
        "scene",
        options=(option,),
        status="preparing",
        message="Preparing input…",
    )
    rebuilt: list[str] = []
    messages: list[str] = []
    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._snapshot = None
    dialog._intent = Intent()
    dialog._escape_button = EscapeButton()
    dialog._back_button = EscapeButton()
    dialog._density = DensitySwitch()
    dialog._density_tooltip = Tooltip()
    dialog._rebuild_body = lambda snapshot: rebuilt.append(snapshot.status)
    dialog._update_option_cards = lambda _options: None
    dialog._render_message = lambda snapshot: messages.append(snapshot.message)

    dialog.apply(idle)
    dialog.apply(preparing)

    assert rebuilt == ["idle"]
    assert messages == ["Preparing input…"]


def test_current_bounds_is_projected_by_primary_host() -> None:
    class Host:
        def current_bounds(self):
            return PopupBounds(135, 95, 440, 330)

    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._primary_surface_host = Host()

    assert dialog.current_bounds() == PopupBounds(135, 95, 440, 330)


def test_close_releases_projection_without_destroying_shared_host() -> None:
    events: list[str] = []

    class Window:
        def withdraw(self) -> None:
            events.append("hidden")

    class Lifecycle:
        def close(self) -> None:
            events.append("destroyed")

    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._window = Window()
    dialog._lifecycle = Lifecycle()
    dialog._snapshot = object()

    dialog.close()

    assert events == []
    assert dialog._snapshot is None
