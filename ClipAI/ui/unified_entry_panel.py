from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.commands import (
    CloseEntryPanel,
    EntryPanelActionSelected,
    EntryPanelEscape,
    EntryPanelOpenMore,
    EntryPanelSearchChanged,
    EntryPanelSlotSelected,
    EntryPanelToggleDensity,
)
from ClipAI.core.models import EntryPanelOption, EntryPanelSnapshot
from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface
from ClipAI.ui.base_dialog import POPUP_FONT_SIZES, TC_FONT_FAMILY, _Tooltip
from ClipAI.ui.dialog_lifecycle import DialogLifecycle
from ClipAI.ui.popup_layout import PopupLayoutPolicy


class EntryPanelIntentAdapter:
    """Translate toolkit gestures into typed Panel intents."""

    def __init__(self, command_sink: Callable[[object], None]) -> None:
        self._command_sink = command_sink
        self._snapshot: EntryPanelSnapshot | None = None

    def apply(self, snapshot: EntryPanelSnapshot) -> None:
        self._snapshot = snapshot

    def select(self, option: EntryPanelOption) -> None:
        snapshot = self._snapshot
        if snapshot is None or not option.enabled:
            return
        if option.action is not None:
            self._command_sink(
                EntryPanelActionSelected(snapshot.panel_id, option.action)
            )
        elif option.slot is not None:
            self._command_sink(EntryPanelSlotSelected(snapshot.panel_id, option.slot))

    def select_slot(self, slot: int) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(EntryPanelSlotSelected(snapshot.panel_id, slot))

    def open_more(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(EntryPanelOpenMore(snapshot.panel_id))

    def search(self, text: str) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(EntryPanelSearchChanged(snapshot.panel_id, text))

    def toggle_density(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(EntryPanelToggleDensity(snapshot.panel_id))

    def escape(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(EntryPanelEscape(snapshot.panel_id))

    def close(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(CloseEntryPanel(snapshot.panel_id))


class UnifiedEntryPanelDialog:
    """Toolkit-only cursor-adjacent projection of the Unified Entry Panel."""

    def __init__(
        self,
        master,
        command_sink: Callable[[object], None],
        native_window_surface: NativeWindowSurface,
        display_metrics: DisplayMetricsReader,
    ) -> None:
        self._native_window_surface = native_window_surface
        self._display_metrics = display_metrics
        self._intent = EntryPanelIntentAdapter(command_sink)
        self._snapshot: EntryPanelSnapshot | None = None
        self._search_guard = False
        self._option_buttons: list[ctk.CTkButton] = []

        self._window = ctk.CTkToplevel(master)
        self._window.withdraw()
        self._window.title("ClipAI")
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.configure(fg_color=("#F4F6F8", "#17191C"))
        self._window.bind("<Escape>", self._on_escape)
        self._window.bind("<KeyPress>", self._on_key)
        self._window.bind("<FocusOut>", self._on_focus_out, add="+")
        self._window.bind("<Return>", self._on_enter)
        self._window.bind("<Down>", lambda event: self._move_focus(event, True))
        self._window.bind("<Up>", lambda event: self._move_focus(event, False))
        self._window.protocol("WM_DELETE_WINDOW", self._intent.close)
        self._lifecycle = DialogLifecycle(
            self._window,
            owns_mainloop=False,
            window_activator=lambda window: self._native_window_surface.activate(
                int(window.winfo_id())
            ),
        )

        self._shell = ctk.CTkFrame(
            self._window,
            corner_radius=14,
            border_width=1,
            border_color=("#CED4DA", "#3B3F45"),
            fg_color=("#FFFFFF", "#202327"),
        )
        self._shell.pack(fill="both", expand=True, padx=1, pady=1)
        self._shell.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self._shell, fg_color="transparent")
        header.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="ClipAI",
            anchor="w",
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["interface"],
                weight="bold",
            ),
        ).grid(row=0, column=0, sticky="w")
        self._density = ctk.CTkSwitch(
            header,
            text="",
            width=38,
            command=self._intent.toggle_density,
        )
        self._density.grid(row=0, column=1, padx=(14, 16))
        self._density_tooltip = _Tooltip(
            self._density,
            "顯示詳細說明，點擊切換精簡模式",
            self._lifecycle,
        )
        self._escape_hint = ctk.CTkLabel(
            header,
            text="Esc 關閉",
            text_color=("#6C757D", "#A6ABB2"),
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
        )
        self._escape_hint.grid(row=0, column=2, sticky="e")

        self._body = ctk.CTkFrame(self._shell, fg_color="transparent")
        self._body.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self._body.grid_columnconfigure(0, weight=1)

    def apply(self, snapshot: EntryPanelSnapshot) -> None:
        self._snapshot = snapshot
        self._intent.apply(snapshot)
        self._escape_hint.configure(
            text="Esc 關閉" if snapshot.page == "root" else "Esc 返回"
        )
        if snapshot.density == "compact":
            self._density.select()
            tooltip = "精簡模式，點擊顯示詳細說明"
        else:
            self._density.deselect()
            tooltip = "顯示詳細說明，點擊切換精簡模式"
        self._density_tooltip.set_text(tooltip)
        self._rebuild_body(snapshot)

    def show(self, snapshot: EntryPanelSnapshot) -> None:
        self.apply(snapshot)
        bounds = PopupLayoutPolicy().calculate(self._display_metrics.current())
        self._window.geometry(
            f"{max(420, bounds.width)}x{bounds.height}+{bounds.x}+{bounds.y}"
        )
        self._window.update_idletasks()
        self._native_window_surface.hide_from_task_switcher(int(self._window.winfo_id()))
        self._window.deiconify()
        self._lifecycle.focus(self._first_focus_target())

    def close(self) -> None:
        self._lifecycle.close()

    def _rebuild_body(self, snapshot: EntryPanelSnapshot) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        self._option_buttons.clear()
        row = 0
        if snapshot.page == "more":
            self._search_guard = True
            search = ctk.CTkEntry(
                self._body,
                placeholder_text="搜尋更多功能",
                font=ctk.CTkFont(
                    family=TC_FONT_FAMILY,
                    size=POPUP_FONT_SIZES["interface"],
                ),
            )
            search.insert(0, snapshot.search_text)
            search.grid(row=row, column=0, pady=(0, 8), sticky="ew")
            search.bind("<KeyRelease>", lambda _event: self._intent.search(search.get()))
            self._search_guard = False
            row += 1

        for option in snapshot.options:
            text = self._option_text(option, snapshot)
            button = ctk.CTkButton(
                self._body,
                text=text,
                anchor="w",
                height=40 if snapshot.density == "compact" else 52,
                corner_radius=9,
                border_width=1,
                border_color=("#D7DCE1", "#41464D"),
                fg_color=("#F8F9FA", "#292D32"),
                hover_color=("#E9F2FA", "#263B4D"),
                text_color=("#202428", "#F1F3F5"),
                font=ctk.CTkFont(
                    family=TC_FONT_FAMILY,
                    size=POPUP_FONT_SIZES["interface"],
                ),
                command=lambda selected=option: self._intent.select(selected),
                state="normal" if option.enabled else "disabled",
            )
            button.grid(row=row, column=0, pady=3, sticky="ew")
            self._option_buttons.append(button)
            row += 1

        if snapshot.page == "scene":
            ctk.CTkButton(
                self._body,
                text="＋ 更多功能",
                height=34,
                fg_color="transparent",
                hover_color=("#ECEFF1", "#30343A"),
                text_color=("#5D636A", "#B8BDC4"),
                command=self._intent.open_more,
            ).grid(row=row, column=0, pady=(8, 0), sticky="ew")
            row += 1

        if snapshot.message:
            ctk.CTkLabel(
                self._body,
                text=snapshot.message,
                anchor="w",
                justify="left",
                wraplength=380,
                text_color=("#9B2C2C", "#F6A9A9") if snapshot.status == "error" else ("#5D636A", "#B8BDC4"),
                font=ctk.CTkFont(
                    family=TC_FONT_FAMILY,
                    size=POPUP_FONT_SIZES["auxiliary"],
                ),
            ).grid(row=row, column=0, padx=4, pady=(8, 0), sticky="ew")

    @staticmethod
    def _option_text(option: EntryPanelOption, snapshot: EntryPanelSnapshot) -> str:
        key = f"{option.slot}  " if option.slot is not None else ""
        description = (
            f"\n{option.description}"
            if snapshot.density == "detailed" and option.description
            else ""
        )
        reason = f"\n{option.disabled_reason}" if option.disabled_reason else ""
        return f"{key}{option.label}{description}{reason}"

    def _on_escape(self, _event=None) -> str:
        return "break"

    def _on_key(self, event) -> None:
        if event.char and event.char.isdigit():
            self._intent.select_slot(int(event.char))

    def _on_enter(self, event) -> str:
        invoke = getattr(event.widget, "invoke", None)
        if callable(invoke):
            invoke()
        return "break"

    def _move_focus(self, event, forward: bool) -> str:
        target = event.widget.tk_focusNext() if forward else event.widget.tk_focusPrev()
        if target is not None:
            target.focus_set()
        return "break"

    def _on_focus_out(self, _event=None) -> None:
        self._window.after(0, self._close_if_focus_left)

    def _close_if_focus_left(self) -> None:
        snapshot = self._snapshot
        if snapshot is None or snapshot.status == "preparing":
            return
        try:
            focused = self._window.focus_get()
            if focused is None or focused.winfo_toplevel() is not self._window:
                self._intent.close()
        except tk.TclError:
            pass

    def _first_focus_target(self):
        return self._option_buttons[0] if self._option_buttons else self._density
