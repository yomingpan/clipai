from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

import customtkinter as ctk
from customtkinter.windows.widgets.scaling import ScalingTracker

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
    ACTION_ICON_FONT_FAMILY,
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
from ClipAI.ui.text_layout import fit_single_line_text, fit_tile_title


def recent_tile_tooltip(option: EntryPanelOption) -> str:
    return "\n".join(part for part in (
        option.label, option.description,
        f"長按:{option.long_label}" if option.long_action is not None else "",
        option.disabled_reason,
    ) if part)


_TRANSPARENT_WINDOW_BACKGROUND = "#111111"
_CARD_BACKGROUND = "#252525"
_CARD_HOVER_BACKGROUND = "#303030"
_CARD_BORDER = "#454545"
_PANEL_SECONDARY_TEXT = "#9B9FA3"
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
    """Toolkit-only bottom-center projection of the Unified Entry Panel."""

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
        self._keyboard_navigation_active = False
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
        header.grid(row=0, column=0, padx=16, pady=(14, 0), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        self._back_button = ctk.CTkButton(
            header,
            text="←",
            width=28,
            height=28,
            corner_radius=7,
            fg_color="transparent",
            hover_color="#3A3A3A",
            text_color='#8A8A8A',
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
        self._numeric_hint_label = ctk.CTkLabel(header, text="", height=16, anchor="w", text_color=MODEL_COLOR, font=ctk.CTkFont(family=TC_FONT_FAMILY, size=10))
        self._numeric_hint_label.grid(row=1, column=0, columnspan=4, sticky="ew")
        self._numeric_hint_label.grid_remove()
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
            text='\u00d7',
            width=18,
            height=18,
            corner_radius=9,
            border_width=0,
            fg_color=SURFACE_BG,
            hover_color="#3A3A3A",
            text_color='#8A8A8A',
            font=ctk.CTkFont(
                family=ACTION_ICON_FONT_FAMILY,
                size=10,
                weight='bold',
            ),
            command=self._intent.close,
        )
        self._escape_button.grid(row=0, column=3, sticky="e")
        self._escape_tooltip = _Tooltip(self._escape_button, 'Esc 關閉', self._schedule_lifecycle)

        source_row = ctk.CTkFrame(self._shell, fg_color="transparent")
        source_row.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")
        source_row.grid_columnconfigure(0, weight=1)
        self._source_preview_label = ctk.CTkLabel(
            source_row,
            text="",
            width=1,
            height=18,
            anchor="w",
            justify="left",
            text_color=_PANEL_SECONDARY_TEXT,
            font=ctk.CTkFont(
                family=TC_FONT_FAMILY,
                size=POPUP_FONT_SIZES["auxiliary"],
            ),
        )
        self._source_preview_label.grid(row=0, column=0, sticky="ew")
        tk.Misc.bind(self._source_preview_label, "<Configure>", self._fit_source_preview_text, add="+")
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
            source_row, text="使用剪貼簿", width=136, height=24,
            fg_color="transparent", hover_color="#3A3A3A", text_color=CONTENT_COLOR,
            command=self._intent.use_clipboard,
        )
        self._use_clipboard_button.bind("<FocusIn>", lambda _event: self._refresh_clipboard_focus(), add="+")
        self._use_clipboard_button.bind("<FocusOut>", lambda _event: self._window.after_idle(self._refresh_clipboard_focus), add="+")

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
        clipboard_had_focus = self._clipboard_has_focus()
        self._snapshot = snapshot
        self._intent.apply(snapshot)
        hint = getattr(self, "_numeric_hint_label", None)
        if hint is not None:
            hint.configure(text=snapshot.header_hint)
            if snapshot.header_hint:
                hint.grid()
            else:
                hint.grid_remove()
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
        if clipboard_had_focus and not self._clipboard_visible():
            self._first_focus_target().focus_set()
        self._refresh_clipboard_focus()

    def _clipboard_visible(self) -> bool:
        snapshot = getattr(self, "_snapshot", None)
        return bool(snapshot is not None and snapshot.source_preview is not None and snapshot.source_preview.clipboard_override_available)

    def _clipboard_has_focus(self) -> bool:
        button = getattr(self, "_use_clipboard_button", None)
        try:
            widget = self._window.focus_get()
            while widget is not None:
                if widget is button and button is not None:
                    return True
                widget = getattr(widget, "master", None)
        except (AttributeError, tk.TclError):
            pass
        return False

    def _refresh_clipboard_focus(self) -> None:
        button = getattr(self, "_use_clipboard_button", None)
        if button is not None:
            focused = self._clipboard_visible() and self._clipboard_has_focus()
            button.configure(text="使用剪貼簿（Enter）" if focused else "使用剪貼簿", border_width=1 if focused else 0, border_color=ACTION_COLOR)

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
        self._escape_tooltip._hide()
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
                    height=20,
                ).grid(row=row, column=0, padx=2, pady=(0, 4), sticky="ew")
                row += 1
                recent_frame = ctk.CTkFrame(self._body, fg_color="transparent")
                recent_frame.grid(row=row, column=0, sticky="ew")
                for column in range(3):
                    recent_frame.grid_columnconfigure(column, weight=1, uniform="recent", minsize=60)
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
                text_color=(
                    "#F6A9A9"
                    if preview is not None and preview.kind == "failed"
                    else _PANEL_SECONDARY_TEXT
                ),
            )
            self._fit_source_preview_text()
        if retry is not None:
            if preview is not None and preview.kind == "failed":
                retry.grid(row=0, column=1, padx=(8, 0), sticky="e")
            else:
                retry.grid_forget()

    def _fit_source_preview_text(self, _event=None) -> None:
        label = self._source_preview_label
        preview = self._snapshot.source_preview if self._snapshot is not None else None
        scale = max(.1, ScalingTracker.get_widget_scaling(label))
        available = max(0, label.winfo_width() / scale - 8)
        rendered = fit_single_line_text(
            _source_preview_text(preview),
            width=available,
            measure=label.cget("font").measure,
        )
        if label.cget("text") != rendered:
            label.configure(text=rendered)

    @staticmethod
    def _split_root_options(
        options: tuple[EntryPanelOption, ...],
    ) -> tuple[tuple[EntryPanelOption, ...], tuple[EntryPanelOption, ...]]:
        recent = tuple(
            option
            for option in options
            if option.action is not None and option.slot in {1, 2, 3}
        )
        return recent, tuple(option for option in options if option not in recent)

    def _create_option_card(
        self,
        parent,
        option: EntryPanelOption,
        snapshot: EntryPanelSnapshot,
    ) -> ctk.CTkFrame:
        recent = snapshot.page == "root" and option.action is not None
        card = ctk.CTkFrame(
            parent,
            corner_radius=9,
            border_width=1,
            border_color=_CARD_BORDER,
            fg_color=_CARD_BACKGROUND,
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)
        if recent:
            card.configure(width=60, height=80)
            card.grid_propagate(False)
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
                elif focused and self._keyboard_navigation_active:
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
        if recent:
            title_label.configure(height=34, anchor="nw", font=ctk.CTkFont(family=TC_FONT_FAMILY, size=11, weight="bold"), justify="left")
            title_label.place(x=12, y=29)
        else:
            title_label.grid(row=0, column=0, padx=12, pady=7, sticky="ew")
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
        tile_tooltip = None
        if recent:
            badge = ctk.CTkLabel(
                card,
                text=str(option.slot),
                width=14,
                height=18,
                fg_color="transparent",
                text_color=ACTION_COLOR,
                font=ctk.CTkFont(family=TC_FONT_FAMILY, size=12),
            )
            badge.place(x=12, y=7)
            interactive_widgets.append(badge)
            long_hint_label.configure(height=18)
            long_hint_label.place(relx=1, x=-10, y=7, anchor="ne")
            tile_tooltip = _Tooltip(
                card,
                recent_tile_tooltip(option),
                self._schedule_lifecycle,
                show_on_focus=False,
            )
            card._recent_badge = badge
            card._recent_title = title_label
            card._recent_long_hint = long_hint_label
            card._recent_tooltip = tile_tooltip

            def resize_title(_event=None):
                scale = max(.1, ScalingTracker.get_widget_scaling(card))
                available = max(1, card.winfo_width()/scale-24)
                display_title = (
                    latest_option.long_label
                    if hold["reached"] and latest_option.long_label
                    else latest_option.label
                )
                title_label.configure(width=available, text=fit_tile_title(display_title, width=available, measure=title_label.cget("font").measure))
            card.bind("<Configure>", resize_title, add="+")
            card.bind("<Destroy>", tile_tooltip._hide, add="+")

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
                text_color=CONTENT_COLOR if latest_option.enabled and not latest_option.pending else MODEL_COLOR,
            )
            if recent:
                resize_title()
            else:
                title_label.configure(text=option_title(latest_option))

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
                if recent:
                    resize_title()
                else:
                    title_label.configure(text=latest_option.long_label or option_title(latest_option))
                title_label.configure(text_color=ACTION_COLOR)
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
            if recent:
                tile_tooltip.set_text(recent_tile_tooltip(updated))
                badge.configure(
                    text=str(updated.slot),
                    text_color=ACTION_COLOR if updated.enabled and not updated.pending else MODEL_COLOR,
                )
                long_hint_label.configure(text="長按" if updated.long_action is not None else "")
                title_label.configure(text_color=CONTENT_COLOR if updated.enabled and not updated.pending else MODEL_COLOR)
                resize_title()
                if not updated.enabled or updated.pending:
                    clear_hold()
                    hovered = focused = False
                    card.configure(fg_color=_CARD_BACKGROUND, border_color=_CARD_BORDER)
                else:
                    redraw_card()
                return
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
            if tile_tooltip is not None:
                widget.bind("<Enter>", tile_tooltip._schedule, add="+")
                widget.bind("<Leave>", tile_tooltip._hide, add="+")
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
        if recent:
            tk.Misc.bind(card, "<FocusIn>", show_focus, add="+")
            tk.Misc.bind(card, "<FocusOut>", clear_focus, add="+")
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
        if getattr(event, "keysym", "") in {"Tab", "ISO_Left_Tab", "Up", "Down"}:
            self._keyboard_navigation_active = True
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
        widget = event.widget
        while widget is not None:
            invoke = getattr(widget, "invoke", None)
            if callable(invoke):
                invoke()
                break
            widget = getattr(widget, "master", None)
        return "break"

    def _move_focus(self, event, forward: bool) -> str:
        if not self.is_primary_content_mounted():
            return "break"
        self._keyboard_navigation_active = True
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
        if self._clipboard_visible():
            return self._use_clipboard_button
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
