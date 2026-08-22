from __future__ import annotations

from collections.abc import Callable
from tkinter import filedialog
import tkinter as tk
import uuid

import customtkinter as ctk

from ClipAI.core.commands import (
    ClosePersonalStyles,
    ControlSurfaceActivated,
    ControlSurfaceReleased,
    ImportPersonalStyle,
    SelectPersonalStyle,
)
from ClipAI.core.models import ControlSurfaceRef, PersonalStyleState
from ClipAI.core.ports import NativeWindowSurface
from ClipAI.ui.window_icons import CUSTOMTKINTER_ICON_DELAY_MS, destroy_window_icons, install_clipai_window_icons


class PersonalStylesDialog:
    """Toolkit-only personal-style manager that emits typed intents."""

    def __init__(
        self,
        master,
        command_sink: Callable[[object], None],
        native_window_surface: NativeWindowSurface,
    ) -> None:
        self._command_sink = command_sink
        self._native_window_surface = native_window_surface
        self._state = PersonalStyleState()
        self._profile_by_name: dict[str, str] = {}
        self._window = ctk.CTkToplevel(master)
        self._window.title("ClipAI Personal Styles")
        self._window.geometry("470x390")
        self._window.minsize(430, 360)
        self._window.grid_columnconfigure(0, weight=1)
        self._window.protocol("WM_DELETE_WINDOW", self._request_close)
        self._window_icon_handles: tuple[int, ...] = ()
        self._window.after(CUSTOMTKINTER_ICON_DELAY_MS, self._apply_windows_window_icons)

        ctk.CTkLabel(
            self._window,
            text="Personal Styles",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=24, pady=(22, 6), sticky="ew")
        ctk.CTkLabel(
            self._window,
            text=(
                "Import a UTF-8 Markdown or text style guide. The active guide is sent "
                "to your selected AI provider when you use Ctrl+Alt+I, O, or P."
            ),
            anchor="w",
            justify="left",
            wraplength=410,
        ).grid(row=1, column=0, padx=24, pady=(0, 18), sticky="ew")

        ctk.CTkLabel(self._window, text="Active style", anchor="w").grid(
            row=2, column=0, padx=24, pady=(0, 5), sticky="ew"
        )
        self._selected_name = tk.StringVar(value="No personal style imported")
        self._profiles = ctk.CTkOptionMenu(
            self._window,
            variable=self._selected_name,
            values=["No personal style imported"],
            command=self._select,
        )
        self._profiles.grid(row=3, column=0, padx=24, sticky="ew")

        self._shortcuts = ctk.CTkLabel(
            self._window,
            text=(
                "Ctrl+Alt+I  Private wording\n"
                "Ctrl+Alt+O  Formal spoken delivery\n"
                "Ctrl+Alt+P  Presentation bullets + delivery"
            ),
            anchor="w",
            justify="left",
        )
        self._shortcuts.grid(row=4, column=0, padx=24, pady=(20, 6), sticky="ew")

        self._message = ctk.CTkLabel(
            self._window,
            text="",
            anchor="w",
            justify="left",
            wraplength=410,
        )
        self._message.grid(row=5, column=0, padx=24, pady=(10, 8), sticky="ew")
        self._import = ctk.CTkButton(
            self._window,
            text="Import Style Guide...",
            command=self._choose_file,
        )
        self._import.grid(row=6, column=0, padx=24, pady=(8, 22), sticky="ew")

        self._window.bind("<Escape>", lambda _event: self._handle_escape())
        self._window.bind(
            "<FocusIn>",
            lambda _event: self._command_sink(
                ControlSurfaceActivated(ControlSurfaceRef("personal-styles", "personal_styles"))
            ),
            add="+",
        )
        self._window.bind(
            "<FocusOut>",
            lambda _event: self._window.after(0, self._release_focus_if_outside),
            add="+",
        )

    def apply(self, state: PersonalStyleState) -> None:
        self._state = state
        self._profile_by_name = {profile.name: profile.profile_id for profile in state.profiles}
        values = list(self._profile_by_name) or ["No personal style imported"]
        self._profiles.configure(values=values)
        selected = next(
            (profile.name for profile in state.profiles if profile.profile_id == state.selected_profile_id),
            values[0],
        )
        self._selected_name.set(selected)
        pending = state.operation_state == "pending"
        enabled = "disabled" if pending or not state.profiles else "normal"
        self._profiles.configure(state=enabled)
        self._import.configure(
            state="disabled" if pending else "normal",
            text="Importing..." if pending and state.operation_kind == "import" else "Import Style Guide...",
        )
        self._message.configure(text=state.message)
        self._window.deiconify()
        self._window.lift()

    def _choose_file(self) -> None:
        if self._state.operation_state == "pending":
            return
        path = filedialog.askopenfilename(
            parent=self._window,
            title="Import Personal Style Guide",
            filetypes=(
                ("Style guides", "*.md *.txt"),
                ("Markdown", "*.md"),
                ("Plain text", "*.txt"),
            ),
        )
        if path:
            self._command_sink(ImportPersonalStyle(path, uuid.uuid4().hex))

    def _select(self, name: str) -> None:
        if self._state.operation_state == "pending":
            return
        profile_id = self._profile_by_name.get(name)
        if profile_id and profile_id != self._state.selected_profile_id:
            self._command_sink(SelectPersonalStyle(profile_id, uuid.uuid4().hex))

    def _request_close(self) -> None:
        self._command_sink(ClosePersonalStyles())

    def _handle_escape(self) -> str:
        return "break"

    def _release_focus_if_outside(self) -> None:
        try:
            focused = self._window.focus_get()
            if focused is None or focused.winfo_toplevel() is not self._window:
                self._command_sink(
                    ControlSurfaceReleased(ControlSurfaceRef("personal-styles", "personal_styles"))
                )
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self._window.withdraw()
        except tk.TclError:
            pass

    def _apply_windows_window_icons(self) -> None:
        try:
            self._window_icon_handles = install_clipai_window_icons(
                self._window,
                self._native_window_surface,
            )
        except (OSError, tk.TclError):
            pass

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except tk.TclError:
            pass
        destroy_window_icons(self._native_window_surface, self._window_icon_handles)
        self._window_icon_handles = ()
