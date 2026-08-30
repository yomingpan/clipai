import tkinter as tk

import customtkinter as ctk
import pytest

from ClipAI.core.commands import (
    EntryPanelActionSelected,
    EntryPanelEscape,
    EntryPanelSlotSelected,
    EntryPanelToggleDensity,
)
from ClipAI.core.models import DisplayMetrics, EntryActionRef, EntryPanelOption, EntryPanelSnapshot
from ClipAI.ui.base_dialog import ACTION_HOVER_COLOR
from ClipAI.ui.unified_entry_panel import EntryPanelIntentAdapter, UnifiedEntryPanelDialog


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
    try:
        dialog = UnifiedEntryPanelDialog(
            master,
            lambda _command: None,
            NativeSurface(),
            MetricsReader(),
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
        dialog.show(snapshot)
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
        if dialog is not None:
            dialog.close()
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
    adapter.escape()

    assert commands == [
        EntryPanelActionSelected("panel-1", action),
        EntryPanelSlotSelected("panel-1", 2),
        EntryPanelToggleDensity("panel-1"),
        EntryPanelEscape("panel-1"),
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


def test_show_places_a_panel_once_and_keeps_that_position_for_projection_updates() -> None:
    class Window:
        def __init__(self) -> None:
            self.geometry_calls: list[str] = []

        def geometry(self, value: str) -> None:
            self.geometry_calls.append(value)

        def update_idletasks(self) -> None:
            pass

        def winfo_id(self) -> int:
            return 42

        def deiconify(self) -> None:
            pass

    class NativeSurface:
        def hide_from_task_switcher(self, _window_id: int) -> None:
            pass

    class Metrics:
        def __init__(self) -> None:
            self.calls = 0

        def current(self) -> DisplayMetrics:
            self.calls += 1
            return DisplayMetrics(1.0, 0, 0, 1920, 1080, 400 + self.calls, 300)

    class Lifecycle:
        def focus(self, _target: object) -> None:
            pass

    dialog = UnifiedEntryPanelDialog.__new__(UnifiedEntryPanelDialog)
    dialog._window = Window()
    dialog._native_window_surface = NativeSurface()
    dialog._display_metrics = Metrics()
    dialog._lifecycle = Lifecycle()
    dialog._placed_panel_id = None
    dialog.apply = lambda _snapshot: None
    dialog._first_focus_target = lambda: None

    dialog.show(EntryPanelSnapshot("panel-1", "root"))
    dialog.show(EntryPanelSnapshot("panel-1", "root", density="compact"))

    assert dialog._display_metrics.calls == 1
    assert len(dialog._window.geometry_calls) == 1
