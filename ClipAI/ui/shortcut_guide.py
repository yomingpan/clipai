from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.commands import CloseShortcutGuide, ControlSurfaceActivated, ControlSurfaceReleased, SelectShortcutGuideItem
from ClipAI.core.hotkeys import GRAVE_KEY_TOKEN
from ClipAI.core.models import ControlSurfaceRef, ShortcutGuideItem, ShortcutGuideSnapshot
from ClipAI.core.ports import NativeWindowSurface
from ClipAI.ui.window_icons import CUSTOMTKINTER_ICON_DELAY_MS, destroy_window_icons, install_clipai_window_icons


_KEY_ROWS = (
    (("~", GRAVE_KEY_TOKEN), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"), ("0", "0")),
    (("Q", "q"), ("W", "w"), ("E", "e"), ("R", "r"), ("T", "t"), ("Y", "y"), ("U", "u"), ("I", "i"), ("O", "o"), ("P", "p")),
    (("A", "a"), ("S", "s"), ("D", "d"), ("F", "f"), ("G", "g"), ("H", "h"), ("J", "j"), ("K", "k"), ("L", "l")),
    (("Z", "z"), ("X", "x"), ("C", "c"), ("V", "v"), ("B", "b"), ("N", "n"), ("M", "m")),
    (("Ctrl", "ctrl"), ("Alt", "alt")),
)
_KEY_DEFAULT = ("gray84", "gray22")
_KEY_SELECTED = ("#D8EAFB", "#244D73")
_KEY_PRESSED = ("#C7E8CB", "#236B38")


class ShortcutGuideDialog:
    """Toolkit-only projection of the shortcut guide."""

    def __init__(self, master, command_sink: Callable[[object], None], native_window_surface: NativeWindowSurface) -> None:
        self._command_sink = command_sink
        self._native_window_surface = native_window_surface
        self._snapshot: ShortcutGuideSnapshot | None = None
        self._window_icon_handles: tuple[int, ...] = ()
        self._list_buttons: dict[str, ctk.CTkButton] = {}
        self._list_signature: tuple[tuple[str, str, str], ...] = ()
        self._key_labels: dict[str, ctk.CTkLabel] = {}

        self._window = ctk.CTkToplevel(master)
        self._window.title("ClipAI Keyboard Shortcuts")
        self._window.geometry("900x640")
        self._window.minsize(780, 560)
        self._window.protocol("WM_DELETE_WINDOW", self._request_close)
        self._window.bind("<Escape>", lambda _event: self._handle_escape())
        self._window.bind("<FocusIn>", lambda _event: self._focus_changed(True), add="+")
        self._window.bind("<FocusOut>", lambda _event: self._window.after(
            0, self._release_focus_if_outside
        ), add="+")
        self._window.grid_columnconfigure(0, weight=1)
        self._window.grid_rowconfigure(2, weight=1)
        self._window.after(CUSTOMTKINTER_ICON_DELAY_MS, self._apply_window_icons)

        ctk.CTkLabel(
            self._window,
            text="快捷鍵指南與測試",
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="ew")
        self._instruction = ctk.CTkLabel(
            self._window,
            text="請按住 Ctrl + Alt，再按一個功能鍵。練習模式不會執行 Action；Esc 關閉指南。",
            anchor="w",
            justify="left",
            wraplength=840,
        )
        self._instruction.grid(row=1, column=0, padx=24, pady=(0, 16), sticky="ew")

        body = ctk.CTkFrame(self._window, fg_color="transparent")
        body.grid(row=2, column=0, padx=24, pady=(0, 20), sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=310)
        body.grid_columnconfigure(1, weight=1)

        self._shortcut_list = ctk.CTkScrollableFrame(body, label_text="全部快捷鍵", width=300)
        self._shortcut_list.grid(row=0, column=0, padx=(0, 16), sticky="nsew")
        self._shortcut_list.grid_columnconfigure(0, weight=1)

        detail = ctk.CTkFrame(body)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(detail, text="鍵盤位置", anchor="w", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(18, 8), sticky="ew"
        )
        keyboard = ctk.CTkFrame(detail, fg_color="transparent")
        keyboard.grid(row=1, column=0, padx=18, sticky="ew")
        self._build_keyboard(keyboard)

        self._status = ctk.CTkLabel(
            detail,
            text="",
            anchor="w",
            justify="left",
            wraplength=500,
            corner_radius=8,
            fg_color=("gray90", "gray17"),
        )
        self._status.grid(row=2, column=0, padx=20, pady=(18, 12), ipady=10, sticky="ew")

        self._title = ctk.CTkLabel(detail, text="", anchor="w", font=ctk.CTkFont(size=18, weight="bold"))
        self._title.grid(row=3, column=0, padx=20, pady=(4, 4), sticky="ew")
        self._description = ctk.CTkLabel(detail, text="", anchor="nw", justify="left", wraplength=500)
        self._description.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="nsew")

    def apply(self, snapshot: ShortcutGuideSnapshot) -> None:
        self._snapshot = snapshot
        self._rebuild_list(snapshot)
        item = next((entry for entry in snapshot.items if entry.shortcut_id == snapshot.selected_shortcut_id), None)
        if item is not None:
            modifiers = " + ".join(item.display_hotkey.split(" + ")[:-1])
            self._instruction.configure(text=f"請按住 {modifiers}，再按一個功能鍵。練習模式不會執行 Action；Esc 關閉指南。")
        self._apply_keyboard(item, snapshot.pressed_keys)
        self._status.configure(text=snapshot.status_text)
        self._apply_detail(item)

    def show(self, snapshot: ShortcutGuideSnapshot) -> None:
        self.apply(snapshot)
        self._window.deiconify()
        self._window.lift()

    def close(self) -> None:
        try:
            self._window.withdraw()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except tk.TclError:
            pass
        destroy_window_icons(self._native_window_surface, self._window_icon_handles)
        self._window_icon_handles = ()

    def _build_keyboard(self, parent) -> None:
        for row_index, row in enumerate(_KEY_ROWS):
            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.grid(row=row_index, column=0, pady=2, sticky="w")
            if row_index == 2:
                row_frame.grid_configure(padx=(14, 0))
            elif row_index == 3:
                row_frame.grid_configure(padx=(28, 0))
            elif row_index == 4:
                row_frame.grid_configure(pady=(10, 2))
            for label, token in row:
                key = ctk.CTkLabel(
                    row_frame,
                    text=label,
                    width=56 if token in {"ctrl", "alt"} else 36,
                    height=32,
                    corner_radius=6,
                    fg_color=_KEY_DEFAULT,
                )
                key.pack(side="left", padx=2)
                self._key_labels[token] = key

    def _rebuild_list(self, snapshot: ShortcutGuideSnapshot) -> None:
        signature = tuple(
            (item.shortcut_id, item.display_hotkey, item.title)
            for item in snapshot.items
        )
        if signature != self._list_signature:
            for button in self._list_buttons.values():
                button.destroy()
            self._list_buttons.clear()
            for row, item in enumerate(snapshot.items):
                button = ctk.CTkButton(
                    self._shortcut_list,
                    anchor="w",
                    hover_color=("gray75", "gray30"),
                    command=lambda shortcut_id=item.shortcut_id: self._command_sink(
                        SelectShortcutGuideItem(shortcut_id)
                    ),
                )
                button.grid(row=row, column=0, padx=4, pady=2, sticky="ew")
                self._list_buttons[item.shortcut_id] = button
            self._list_signature = signature

        verified_ids = {shortcut_id for shortcut_id, _press_type in snapshot.verified}
        for item in snapshot.items:
            selected = item.shortcut_id == snapshot.selected_shortcut_id
            marker = "✓ " if item.shortcut_id in verified_ids else ""
            self._list_buttons[item.shortcut_id].configure(
                text=f"{marker}{item.display_hotkey}  ·  {item.title}",
                fg_color=("#3B8ED0", "#1F6AA5") if selected else "transparent",
                text_color=("white", "white") if selected else ("gray10", "gray90"),
            )

    def _apply_keyboard(self, item: ShortcutGuideItem | None, pressed_keys: frozenset[str]) -> None:
        selected_tokens = item.key_tokens if item is not None else frozenset()
        for token, label in self._key_labels.items():
            color = _KEY_PRESSED if token in pressed_keys else (_KEY_SELECTED if token in selected_tokens else _KEY_DEFAULT)
            label.configure(fg_color=color)

    def _apply_detail(self, item: ShortcutGuideItem | None) -> None:
        if item is None:
            self._title.configure(text="目前沒有可用快捷鍵")
            self._description.configure(text="")
            return
        self._title.configure(text=f"{item.display_hotkey}  ·  {item.title}")
        details = f"短按\n{item.short_description}"
        if item.long_title:
            details += f"\n\n長按 · {item.long_title}\n{item.long_description}"
        self._description.configure(text=details)

    def _request_close(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None:
            self._command_sink(CloseShortcutGuide(snapshot.guide_id))

    def _handle_escape(self) -> str:
        return "break"

    def _focus_changed(self, focused: bool) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        command = ControlSurfaceActivated if focused else ControlSurfaceReleased
        self._command_sink(command(ControlSurfaceRef(snapshot.guide_id, "shortcut_guide")))

    def _release_focus_if_outside(self) -> None:
        try:
            focused = self._window.focus_get()
            if focused is None or focused.winfo_toplevel() is not self._window:
                self._focus_changed(False)
        except tk.TclError:
            pass

    def _apply_window_icons(self) -> None:
        try:
            self._window_icon_handles = install_clipai_window_icons(self._window, self._native_window_surface)
        except (OSError, tk.TclError):
            pass
