from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ClipAI.core.event_bus import get_event_bus
from ClipAI.ui.dialog_lifecycle import DialogLifecycle


class BaseDialog:
    def __init__(
        self,
        *,
        title: str,
        width: int,
        height: int,
        position: str = "center",
        border_color: str = "#D8DEE8",
        track_dialog_state: bool = True,
    ) -> None:
        del track_dialog_state
        self.pending_tasks: list[str] = []
        self._valid = True

        try:
            self.root = ctk.CTk()
            self.root.title(title)
            self.root.geometry(f"{width}x{height}")
            self.root.minsize(min(width, 320), min(height, 180))
            self.root.configure(fg_color=("#F7F8FA", "#111318"))
            self._position_window(width, height, position)

            self.main_frame = ctk.CTkFrame(
                self.root,
                fg_color=("white", "#181B22"),
                corner_radius=14,
                border_width=1,
                border_color=border_color,
            )
            self.main_frame.pack(fill="both", expand=True, padx=14, pady=14)

            self.lifecycle = DialogLifecycle(get_event_bus(), self.root)
            self.root.protocol("WM_DELETE_WINDOW", self.lifecycle.close)
            self.root.bind("<Escape>", lambda _event: self.lifecycle.close())
        except Exception:
            self._valid = False
            raise

    def is_valid(self) -> bool:
        return self._valid

    def _position_window(self, width: int, height: int, position: str) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        if position == "cursor":
            try:
                pointer_x = self.root.winfo_pointerx()
                pointer_y = self.root.winfo_pointery()
                x = max(20, min(pointer_x - width // 3, screen_w - width - 20))
                y = max(20, min(pointer_y - height // 4, screen_h - height - 40))
            except tk.TclError:
                x = max(20, (screen_w - width) // 2)
                y = max(20, (screen_h - height) // 2)
        else:
            x = max(20, (screen_w - width) // 2)
            y = max(20, (screen_h - height) // 2)

        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def run_dialog(self) -> None:
        self.lifecycle.run_dialog()
