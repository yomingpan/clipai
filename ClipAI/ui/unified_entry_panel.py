from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.commands import (
    CloseEntryPanel,
    EntryPanelActionSelected,
    EntryPanelBack,
    EntryPanelOpenMore,
    EntryPanelSearchChanged,
    EntryPanelSlotSelected,
    EntryPanelToggleDensity,
    RetryEntryPanelInput,
    UseEntryPanelClipboard,
)
from ClipAI.core.models import EntryInputSourcePreview, EntryPanelOption, EntryPanelSnapshot, PopupBounds, PressType
from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface
from ClipAI.ui.ime_composition import install_ime_composition_font
from ClipAI.ui.base_dialog import (
    ACTION_COLOR,
    ACTION_HOVER_COLOR,
    CONTENT_COLOR,
    MODEL_COLOR,
    POPUP_FONT_SIZES,
    SURFACE_BG,
    TC_FONT_FAMILY,
    _Tooltip,
    install_ime_halfwidth_punctuation_fix,
)
from ClipAI.ui.dialog_lifecycle import DialogLifecycle
from ClipAI.ui.popup_layout import PopupLayoutPolicy
from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceLease


_TRANSPARENT_WINDOW_BACKGROUND = "#111111"
_CARD_BACKGROUND = "#252525"
_CARD_HOVER_BACKGROUND = "#303030"
_CARD_BORDER = "#454545"
_HOLD_SEC = 0.5
_HOLD_STEPS = 12
_KEY_RELEASE_DEBOUNCE_MS = 30


class EntryPanelIntentAdapter:
    """Translate toolkit gestures into typed Panel intents."""

    def __init__(self, command_sink: Callable[[object], None]) -> None:
        self._command_sink = command_sink
        self._snapshot: EntryPanelSnapshot | None = None
        self._selection_pending = False

    def apply(self, snapshot: EntryPanelSnapshot) -> None:
        if snapshot != self._snapshot:
            self._selection_pending = False
        self._snapshot = snapshot

    def select(self, option: EntryPanelOption, *, press: PressType = "short") -> None:
        snapshot = self._snapshot
        if (
            snapshot is None
            or not option.enabled
            or option.pending
            or self._selection_pending
        ):
            return
        action = (
            option.long_action
            if press == "long" and option.long_action is not None
            else option.action
        )
        if action is not None:
            self._selection_pending = True
            self._command_sink(
                EntryPanelActionSelected(snapshot.panel_id, action)
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

    def back(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(EntryPanelBack(snapshot.panel_id))

    def close(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(CloseEntryPanel(snapshot.panel_id))

    def retry_input(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(RetryEntryPanelInput(snapshot.panel_id))

    def use_clipboard(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(UseEntryPanelClipboard(snapshot.panel_id))


class UnifiedEntryPanelDialog:
    """Toolkit-only cursor-adjacent projection of the Unified Entry Panel."""

    def __init__(
        self,
        master,
        command_sink: Callable[[object], None],
        native_window_surface: NativeWindowSurface,
        display_metrics: DisplayMetricsReader,
        layout_policy: PopupLayoutPolicy | None = None,
        *,
        primary_surface_host: PrimarySurfaceHost | None = None,
        primary_surface_lease: PrimarySurfaceLease | None = None,
    ) -> None:
        del display_metrics, layout_policy
        self._native_window_surface = native_window_surface
        self._intent = EntryPanelIntentAdapter(command_sink)
        self._snapshot: EntryPanelSnapshot | None = None
        self._search_guard = False
        self._option_buttons: list[tk.Misc] = []
        self._option_updaters: list[Callable[[EntryPanelOption], None]] = []
        self._hold_controllers: dict[int, dict[str, Callable]] = {}
        self._key_hold: dict[str, object] | None = None
        self._key_release_job: object | None = None
        self._placed_panel_id: str | None = None
        self._body_render_key: tuple[object, ...] | None = None
        self._message_label: ctk.CTkLabel | None = None
        self._message_row = 0
        self._primary_surface_host = primary_surface_host
        self._primary_surface_lease = primary_surface_lease
        if primary_surface_host is None or primary_surface_lease is None:
            raise ValueError("UnifiedEntryPanelDialog requires a primary surface host and lease")
        self._window = primary_surface_host.window
        self._lifecycle = primary_surface_host.lifecycle
        # Panel-owned delayed work must be cancellable on reclaim without
        # cancelling jobs that belong to a Popup mounted in the same host.
        self._schedule_lifecycle = DialogLifecycle(
            self._window,
            owns_mainloop=False,
        )
        self._window.bind("<Escape>", self._on_escape, add="+")
        self._window.bind("<Control-z>", self._on_back, add="+")
        self._window.bind("<KeyPress>", self._on_key, add="+")
        self._window.bind("<KeyRelease>", self._on_key_release, add="+")
        self._window.bind("<FocusOut>", self._on_focus_out, add="+")
        self._window.bind("<Return>", self._on_enter, add="+")
        self._window.bind("<Down>", lambda event: self._move_focus(event, True), add="+")
        self._window.bind("<Up>", lambda event: self._move_focus(event, False), add="+")

        self._shell = ctk.CTkFrame(
            self._window,
            corner_radius=18,
            border_width=1,
            border_color="#454545",
            fg_color=SURFACE_BG,
        )
        self._shell.grid_columnconfigure(0, weight=1)
        self._shell.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self._shell, fg_color="transparent")
        header.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        self._back_button = ctk.CTkButton(
            header,
            text="←",
            width=28,
            height=28,
            corner_radius=7,
            fg_color="transparent",
            hover_color="#3A3A3A",
            text_color=CONTENT_COLOR,
            command=self._intent.back,
        )
        self._back_button.grid(row=0, column=0, padx=(0, 8), sticky="w")
        title_label = ctk.CTkLabel(
            header,
            text="ClipAI",
            anchor="w",
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["interface"],
                weight="bold",
            ),
        )
        title_label.grid(row=0, column=1, sticky="w")
        self._density = ctk.CTkSwitch(
            header,
            text="",
            width=38,
            command=self._intent.toggle_density,
        )
        self._density.grid(row=0, column=2, padx=(14, 16))
        self._density_tooltip = _Tooltip(
            self._density,
            "顯示詳細說明，點擊切換精簡模式",
            self._schedule_lifecycle,
        )
        self._escape_button = ctk.CTkButton(
            header,
            text="Esc 關閉",
            width=74,
            height=28,
            corner_radius=7,
            border_width=1,
            border_color="#4A4A4A",
            fg_color="transparent",
            hover_color="#3A3A3A",
            text_color=CONTENT_COLOR,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
            command=self._intent.close,
        )
        self._escape_button.grid(row=0, column=3, sticky="e")

        source_row = ctk.CTkFrame(self._shell, fg_color="transparent")
        source_row.grid(row=1, column=0, padx=16, pady=(0, 7), sticky="ew")
        source_row.grid_columnconfigure(0, weight=1)
        self._source_preview_label = ctk.CTkLabel(
            source_row,
            text="",
            anchor="w",
            justify="left",
            text_color=MODEL_COLOR,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
        )
        self._source_preview_label.grid(row=0, column=0, sticky="ew")
        self._retry_input_button = ctk.CTkButton(
            source_row,
            text="重試",
            width=54,
            height=24,
            fg_color="transparent",
            hover_color="#3A3A3A",
            text_color=CONTENT_COLOR,
            command=self._intent.retry_input,
        )
        self._use_clipboard_button = ctk.CTkButton(
            source_row, text="使用剪貼簿", width=92, height=24,
            fg_color="transparent", hover_color="#3A3A3A", text_color=CONTENT_COLOR,
            command=self._intent.use_clipboard,
        )

        self._body = ctk.CTkScrollableFrame(
            self._shell,
            corner_radius=0,
            fg_color="transparent",
            scrollbar_button_color="#454545",
            scrollbar_button_hover_color="#5A5A5A",
        )
        self._body.grid(row=2, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self._body.grid_columnconfigure(0, weight=1)
        self._drag_controller = None
        primary_surface_host.bind_drag(header, title_label)

    def apply(self, snapshot: EntryPanelSnapshot) -> None:
        self._snapshot = snapshot
        self._intent.apply(snapshot)
        self._render_source_preview(snapshot.source_preview)
        if snapshot.page == "root":
            self._back_button.grid_remove()
        else:
            self._back_button.grid()
        if snapshot.density == "detailed":
            self._density.select()
            tooltip = "詳細模式，點擊切換精簡模式"
        else:
            self._density.deselect()
            tooltip = "精簡模式，點擊顯示詳細說明"
        self._density_tooltip.set_text(tooltip)
        body_render_key = _body_render_key(snapshot)
        if body_render_key != getattr(self, "_body_render_key", None):
            self._rebuild_body(snapshot)
            self._body_render_key = body_render_key
        else:
            self._update_option_cards(snapshot.options)
            self._render_message(snapshot)

    def show(
        self,
        snapshot: EntryPanelSnapshot,
        *,
        anchor: PopupBounds | None = None,
    ) -> None:
        if snapshot != getattr(self, "_snapshot", None):
            self.apply(snapshot)
        del anchor
        if self.is_primary_content_mounted() and snapshot.status != "preparing":
            self._lifecycle.focus(self._first_focus_target())

    def hide(self) -> None:
        self.unmount_primary_content()

    def reveal(self) -> None:
        snapshot = self._snapshot
        if (
            self.is_primary_content_mounted()
            and snapshot is not None
            and snapshot.status != "preparing"
        ):
            self._lifecycle.focus(self._first_focus_target())

    def current_bounds(self) -> PopupBounds | None:
        """Capture the actual user-adjusted outer bounds for Popup handoff."""
        return self._primary_surface_host.current_bounds()

    def presents(self, panel_id: str) -> bool:
        snapshot = self._snapshot
        return snapshot is not None and snapshot.panel_id == panel_id

    def close(self) -> None:
        self._cancel_key_hold()
        self._density_tooltip._hide()
        self._schedule_lifecycle.cancel_scheduled()
        self._snapshot = None

    @property
    def primary_surface_host(self) -> PrimarySurfaceHost | None:
        return self._primary_surface_host

    @property
    def primary_surface_lease(self) -> PrimarySurfaceLease | None:
        return self._primary_surface_lease

    def mount_primary_content(self) -> bool:
        try:
            self._shell.pack(fill="both", expand=True)
        except tk.TclError:
            return False
        return True

    def unmount_primary_content(self) -> None:
        try:
            self._shell.pack_forget()
        except tk.TclError:
            pass

    def is_primary_content_mounted(self) -> bool:
        host = getattr(self, "_primary_surface_host", None)
        lease = getattr(self, "_primary_surface_lease", None)
        return host is None or (lease is not None and host.is_mounted(lease))

    def request_close(self) -> None:
        """Request runtime-owned Panel closure after an external click."""
        self._intent.close()

    def contains_screen_point(self, x: int, y: int) -> bool:
        try:
            self._window.update_idletasks()
            left = int(self._window.winfo_rootx())
            top = int(self._window.winfo_rooty())
            width = int(self._window.winfo_width())
            height = int(self._window.winfo_height())
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return False
        return left <= x < left + width and top <= y < top + height

    def _rebuild_body(self, snapshot: EntryPanelSnapshot) -> None:
        self._cancel_key_hold()
        self._hold_controllers.clear()
        self._message_label = None
        for child in self._body.winfo_children():
            child.destroy()
        self._option_buttons.clear()
        self._option_updaters.clear()
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
            install_ime_halfwidth_punctuation_fix(search)
            install_ime_composition_font(search, self._native_window_surface)
            self._search_guard = False
            row += 1

        options = snapshot.options
        if snapshot.page == "root":
            recent, options = self._split_root_options(options)
            if recent:
                ctk.CTkLabel(
                    self._body,
                    text="最近使用",
                    anchor="w",
                    text_color=CONTENT_COLOR,
                    font=ctk.CTkFont(
                        family=TC_FONT_FAMILY,
                        size=POPUP_FONT_SIZES["interface"],
                        weight="bold",
                    ),
                ).grid(row=row, column=0, padx=2, pady=(0, 5), sticky="ew")
                row += 1
                recent_frame = ctk.CTkFrame(self._body, fg_color="transparent")
                recent_frame.grid(row=row, column=0, sticky="ew")
                for column in range(3):
                    recent_frame.grid_columnconfigure(column, weight=1, uniform="recent")
                for column, option in enumerate(recent):
                    self._create_option_card(
                        recent_frame,
                        option,
                        snapshot,
                    ).grid(row=0, column=column, padx=3, sticky="nsew")
                row += 1
                divider = ctk.CTkFrame(
                    self._body,
                    height=2,
                    corner_radius=0,
                    fg_color=_CARD_BORDER,
                )
                divider.grid_propagate(False)
                divider.grid(row=row, column=0, padx=2, pady=(13, 10), sticky="ew")
                row += 1

        for option in options:
            self._create_option_card(self._body, option, snapshot).grid(
                row=row,
                column=0,
                pady=3,
                sticky="ew",
            )
            row += 1

        if snapshot.page == "scene":
            ctk.CTkButton(
                self._body,
                text="＋ 更多功能",
                height=34,
                fg_color="transparent",
                hover_color="#3A3A3A",
                text_color=CONTENT_COLOR,
                command=self._intent.open_more,
            ).grid(row=row, column=0, pady=(8, 0), sticky="ew")
            row += 1

        self._message_row = row
        self._render_message(snapshot)

    def _render_message(self, snapshot: EntryPanelSnapshot) -> None:
        label = getattr(self, "_message_label", None)
        if not snapshot.message:
            if label is not None:
                label.destroy()
                self._message_label = None
            return
        text_color = "#F6A9A9" if snapshot.status == "error" else MODEL_COLOR
        if label is not None:
            label.configure(text=snapshot.message, text_color=text_color)
            return
        self._message_label = ctk.CTkLabel(
            self._body,
            text=snapshot.message,
            anchor="w",
            justify="left",
            wraplength=380,
            text_color=text_color,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
        )
        self._message_label.grid(
            row=getattr(self, "_message_row", 0),
            column=0,
            padx=4,
            pady=(8, 0),
            sticky="ew",
        )

    def _render_source_preview(
        self,
        preview: EntryInputSourcePreview | None,
    ) -> None:
        label = getattr(self, "_source_preview_label", None)
        retry = getattr(self, "_retry_input_button", None)
        clipboard = getattr(self, "_use_clipboard_button", None)
        if clipboard is not None:
            if preview is not None and preview.clipboard_override_available:
                clipboard.grid(row=1, column=0, pady=(4, 0), sticky="w")
            else:
                clipboard.grid_forget()
        if label is not None:
            label.configure(
                text=_source_preview_text(preview),
                text_color=(
                    "#F6A9A9"
                    if preview is not None and preview.kind == "failed"
                    else MODEL_COLOR
                ),
            )
        if retry is not None:
            if preview is not None and preview.kind == "failed":
                retry.grid(row=0, column=1, padx=(8, 0), sticky="e")
            else:
                retry.grid_forget()

    @staticmethod
    def _split_root_options(
        options: tuple[EntryPanelOption, ...],
    ) -> tuple[tuple[EntryPanelOption, ...], tuple[EntryPanelOption, ...]]:
        recent = tuple(
            option
            for option in options
            if option.action is not None and option.slot in {0, 1, 2}
        )
        return recent, tuple(option for option in options if option not in recent)

    def _create_option_card(
        self,
        parent,
        option: EntryPanelOption,
        snapshot: EntryPanelSnapshot,
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            corner_radius=9,
            border_width=1,
            border_color=_CARD_BORDER,
            fg_color=_CARD_BACKGROUND,
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)
        if option.slot is None:
            title = option.label
        else:
            title = f"{option.slot}  {option.label}"

        hovered = False
        focused = False
        latest_option = option
        has_long = option.long_action is not None
        hold: dict[str, object] = {
            "job": None,
            "reached": False,
            "bar": None,
            "progress": 0,
            "started": False,
        }

        def option_title(current: EntryPanelOption) -> str:
            return (
                current.label
                if current.slot is None
                else f"{current.slot}  {current.label}"
            )

        def redraw_card() -> None:
            if not latest_option.enabled or latest_option.pending:
                return
            try:
                if hovered:
                    card.configure(
                        fg_color=_CARD_HOVER_BACKGROUND,
                        border_color=ACTION_HOVER_COLOR,
                    )
                elif focused:
                    card.configure(
                        fg_color=_CARD_BACKGROUND,
                        border_color=ACTION_COLOR,
                    )
                else:
                    card.configure(
                        fg_color=_CARD_BACKGROUND,
                        border_color=_CARD_BORDER,
                    )
            except tk.TclError:
                # A projection update may destroy this card before its queued
                # pointer-leave callback runs.
                return

        def is_pointer_over_card() -> bool:
            try:
                widget = card.winfo_containing(
                    card.winfo_pointerx(),
                    card.winfo_pointery(),
                )
                while widget is not None:
                    if widget is card:
                        return True
                    widget = widget.master
            except tk.TclError:
                return False
            return False

        def show_hover(_event=None) -> None:
            nonlocal hovered
            hovered = True
            redraw_card()

        def clear_hover(_event=None) -> None:
            def refresh() -> None:
                nonlocal hovered
                hovered = is_pointer_over_card()
                redraw_card()

            card.after_idle(refresh)

        def activate(_event=None) -> str:
            current = latest_option
            if current.enabled and not current.pending:
                self._intent.select(current)
            return "break"

        def show_focus(_event=None) -> None:
            nonlocal focused
            focused = True
            redraw_card()

        def clear_focus(_event=None) -> None:
            nonlocal focused
            focused = False
            redraw_card()

        title_label = ctk.CTkLabel(
            card,
            text=title,
            anchor="w",
            text_color=CONTENT_COLOR,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["interface"],
                weight="bold",
            ),
        )
        title_label.grid(
            row=0,
            column=0,
            padx=12,
            pady=7,
            sticky="ew",
        )
        interactive_widgets = [card, title_label]
        detail_label = ctk.CTkLabel(
            card,
            text="",
            anchor="w",
            justify="left",
            wraplength=360,
            text_color=MODEL_COLOR,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
        )
        interactive_widgets.append(detail_label)
        long_hint_label = ctk.CTkLabel(
            card,
            text="",
            anchor="w",
            text_color=MODEL_COLOR,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
        )
        interactive_widgets.append(long_hint_label)

        def clear_hold() -> None:
            job = hold["job"]
            if job is not None:
                try:
                    card.after_cancel(job)
                except (AttributeError, tk.TclError):
                    pass
            bar = hold["bar"]
            if bar is not None:
                try:
                    bar.destroy()
                except (AttributeError, tk.TclError):
                    pass
            hold.update(job=None, reached=False, bar=None, progress=0, started=False)
            title_label.configure(
                text=option_title(latest_option),
                text_color=CONTENT_COLOR,
            )

        def step() -> None:
            hold["job"] = None
            if not hold["started"]:
                return
            progress = int(hold["progress"]) + 1
            hold["progress"] = progress
            bar = hold["bar"]
            if bar is not None:
                bar.place_configure(relwidth=min(1.0, progress / _HOLD_STEPS))
            if progress >= _HOLD_STEPS:
                hold["reached"] = True
                title_label.configure(
                    text=latest_option.long_label or option_title(latest_option),
                    text_color=ACTION_COLOR,
                )
                return
            hold["job"] = card.after(
                round(_HOLD_SEC * 1000 / _HOLD_STEPS),
                step,
            )

        def hold_begin() -> None:
            if hold["started"] or not latest_option.enabled or latest_option.pending:
                return
            hold.update(reached=False, progress=0, started=True)
            bar = ctk.CTkFrame(card, height=3, fg_color=ACTION_COLOR)
            bar.place(relx=0, rely=1, anchor="sw", relwidth=0)
            hold["bar"] = bar
            hold["job"] = card.after(
                round(_HOLD_SEC * 1000 / _HOLD_STEPS),
                step,
            )

        def hold_settle() -> bool | None:
            if not hold["started"]:
                return None
            reached = bool(hold["reached"])
            clear_hold()
            return reached

        def do_select(reached: bool) -> None:
            current = latest_option
            if current.enabled and not current.pending:
                self._intent.select(
                    current,
                    press="long" if reached else "short",
                )

        def hold_press(_event=None) -> str:
            hold_begin()
            return "break"

        def hold_release(_event=None) -> str:
            reached = hold_settle()
            if reached is not None:
                do_select(reached)
            return "break"

        def hold_leave(_event=None) -> None:
            if hold["started"]:
                clear_hold()

        def update(updated: EntryPanelOption) -> None:
            nonlocal latest_option, hovered, focused
            latest_option = updated
            detail = updated.disabled_reason or (
                "正在讀取來源內容…"
                if updated.pending
                else updated.description
                if snapshot.density == "detailed"
                else ""
            )
            title_label.grid_configure(pady=(7, 0 if detail else 7))
            detail_label.configure(
                text=detail,
                text_color="#F6A9A9" if updated.disabled_reason else MODEL_COLOR,
            )
            if detail:
                detail_label.grid(
                    row=1,
                    column=0,
                    padx=12,
                    pady=(0, 6),
                    sticky="ew",
                )
            else:
                detail_label.grid_forget()
            if updated.long_action is not None and updated.long_label:
                if snapshot.density == "compact":
                    long_hint_label.configure(
                        text=f"{updated.long_label}  ›",
                        text_color=MODEL_COLOR,
                    )
                    long_hint_label.grid(
                        row=0,
                        column=1,
                        padx=(4, 12),
                        pady=7,
                        sticky="e",
                    )
                else:
                    long_hint_label.configure(
                        text=f"長按 · {updated.long_label}",
                        text_color=MODEL_COLOR,
                    )
                    long_hint_label.grid(
                        row=2,
                        column=0,
                        columnspan=2,
                        padx=12,
                        pady=(0, 6),
                        sticky="ew",
                    )
            else:
                long_hint_label.grid_forget()
            if not updated.enabled or updated.pending:
                if hold["started"]:
                    clear_hold()
                hovered = False
                focused = False
                card.configure(
                    fg_color=_CARD_BACKGROUND,
                    border_color=_CARD_BORDER,
                )
            else:
                redraw_card()

        for widget in interactive_widgets:
            widget.bind("<Enter>", show_hover, add="+")
            widget.bind("<Leave>", clear_hover, add="+")
            if has_long:
                widget.bind("<ButtonPress-1>", hold_press, add="+")
                widget.bind("<ButtonRelease-1>", hold_release, add="+")
                widget.bind("<Leave>", hold_leave, add="+")
            else:
                widget.bind("<Button-1>", activate, add="+")
        card.bind("<Return>", activate, add="+")
        card.bind("<space>", activate, add="+")
        card.bind("<FocusIn>", show_focus, add="+")
        card.bind("<FocusOut>", clear_focus, add="+")
        self._option_buttons.append(card)
        self._option_updaters.append(update)
        if has_long and option.slot is not None:
            self._hold_controllers[option.slot] = {
                "begin": hold_begin,
                "settle": hold_settle,
                "select": do_select,
                "cancel": clear_hold,
            }
        update(option)
        return card

    def _update_option_cards(
        self,
        options: tuple[EntryPanelOption, ...],
    ) -> None:
        if len(options) != len(self._option_updaters):
            self._rebuild_body(self._snapshot)  # type: ignore[arg-type]
            return
        for update, option in zip(self._option_updaters, options):
            update(option)

    @staticmethod
    def _option_text(option: EntryPanelOption, snapshot: EntryPanelSnapshot) -> str:
        key = f"{option.slot}  " if option.slot is not None else ""
        description = (
            f"\n{option.description}"
            if snapshot.density == "detailed" and option.description
            else ""
        )
        reason = f"\n{option.disabled_reason}" if option.disabled_reason else ""
        pending = "\n正在讀取來源內容…" if option.pending and not option.disabled_reason else ""
        return f"{key}{option.label}{description}{reason}{pending}"

    def _on_escape(self, _event=None) -> str | None:
        if not self.is_primary_content_mounted():
            return None
        self._intent.close()
        return "break"

    def _on_back(self, _event=None) -> str | None:
        if not self.is_primary_content_mounted():
            return None
        snapshot = self._snapshot
        if snapshot is not None and snapshot.page != "root":
            self._intent.back()
        return "break"

    @staticmethod
    def _event_digit(event) -> int | None:
        char = getattr(event, "char", "")
        if char and char.isdigit():
            return int(char)
        keysym = str(getattr(event, "keysym", ""))
        if keysym.isdigit():
            return int(keysym)
        if keysym.startswith("KP_") and keysym[3:].isdigit():
            return int(keysym[3:])
        return None

    def _on_key(self, event) -> str | None:
        if not self.is_primary_content_mounted():
            return None
        digit = self._event_digit(event)
        if digit is None:
            return None
        controller = self._hold_controllers.get(digit)
        if controller is None:
            self._cancel_key_hold()
            self._intent.select_slot(digit)
            return "break"
        current = self._key_hold
        if current is not None and current["slot"] == digit:
            self._cancel_key_release_finalize()
            return "break"
        self._cancel_key_hold()
        self._key_hold = {"slot": digit, "controller": controller}
        controller["begin"]()
        return "break"

    def _on_key_release(self, event) -> str | None:
        if not self.is_primary_content_mounted():
            return None
        digit = self._event_digit(event)
        current = self._key_hold
        if digit is None or current is None or current["slot"] != digit:
            return None
        self._cancel_key_release_finalize()
        self._key_release_job = self._window.after(
            _KEY_RELEASE_DEBOUNCE_MS,
            self._finalize_key_hold,
        )
        return "break"

    def _finalize_key_hold(self) -> None:
        self._key_release_job = None
        current, self._key_hold = self._key_hold, None
        if current is None:
            return
        controller = current["controller"]
        reached = controller["settle"]()
        if reached is not None:
            controller["select"](reached)

    def _cancel_key_release_finalize(self) -> None:
        job, self._key_release_job = getattr(self, "_key_release_job", None), None
        if job is not None:
            try:
                self._window.after_cancel(job)
            except (AttributeError, tk.TclError):
                pass

    def _cancel_key_hold(self) -> None:
        self._cancel_key_release_finalize()
        current, self._key_hold = getattr(self, "_key_hold", None), None
        if current is not None:
            current["controller"]["cancel"]()

    def _on_enter(self, event) -> str:
        if not self.is_primary_content_mounted():
            return "break"
        invoke = getattr(event.widget, "invoke", None)
        if callable(invoke):
            invoke()
        return "break"

    def _move_focus(self, event, forward: bool) -> str:
        if not self.is_primary_content_mounted():
            return "break"
        target = event.widget.tk_focusNext() if forward else event.widget.tk_focusPrev()
        if target is not None:
            target.focus_set()
        return "break"

    def _on_focus_out(self, _event=None) -> None:
        if not self.is_primary_content_mounted():
            return
        self._window.after(0, self._close_if_focus_left)

    def _close_if_focus_left(self) -> None:
        snapshot = self._snapshot
        if (
            snapshot is None
            or snapshot.status == "preparing"
            or not self.is_primary_content_mounted()
        ):
            return
        try:
            focused = self._window.focus_get()
            if focused is None or focused.winfo_toplevel() is not self._window:
                self._intent.close()
        except tk.TclError:
            pass

    def _first_focus_target(self):
        return self._option_buttons[0] if self._option_buttons else self._density


def _body_render_key(snapshot: EntryPanelSnapshot) -> tuple[object, ...]:
    """Identify widget topology independently from operation lifecycle state."""
    return (
        snapshot.page,
        snapshot.category_id,
        snapshot.density,
        tuple(
            (
                option.slot,
                option.label,
                option.description if snapshot.density == "detailed" else "",
                option.action,
                option.long_action,
                option.long_label,
                option.category_id,
            )
            for option in snapshot.options
        ),
        snapshot.search_text,
    )


def _source_preview_text(preview: EntryInputSourcePreview | None) -> str:
    if preview is None:
        return "來源：尚未讀取"
    labels = {
        "preparing": "正在讀取選取內容…",
        "selection_text": "選取文字",
        "clipboard_text": "剪貼簿文字",
        "clipboard_image": "剪貼簿截圖",
        "workflow_selection": "Popup 選取文字",
        "workflow_result": "目前結果",
        "failed": "讀取失敗",
    }
    label = labels[preview.kind]
    return f"{label}：{preview.summary}" if preview.summary else label
