from __future__ import annotations

from collections.abc import Callable
import uuid

import customtkinter as ctk

from ClipAI.core.commands import EnableVoiceInput
from ClipAI.core.voice import VoiceSetupId


class VoiceSetupDialog:
    """Explicit first-use consent surface; it never begins recording on its own."""

    def __init__(self, root, command_sink: Callable[[object], None]) -> None:
        self._root = root
        self._command_sink = command_sink
        self._dialog: ctk.CTkToplevel | None = None

    def show(self) -> None:
        if self._dialog is None or not self._dialog.winfo_exists():
            self._dialog = ctk.CTkToplevel(self._root)
            self._dialog.title("Set up Voice Input")
            self._dialog.geometry("430x245")
            self._dialog.resizable(False, False)
            self._dialog.attributes("-topmost", True)
            frame = ctk.CTkFrame(self._dialog)
            frame.pack(fill="both", expand=True, padx=16, pady=16)
            ctk.CTkLabel(frame, text="Enable Voice Input", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(2, 10))
            ctk.CTkLabel(
                frame,
                text=(
                    "Hold Ctrl+Alt+W to dictate, then review before pasting.\n\n"
                    "Your microphone is used only while Push-to-Talk is active. "
                    "Browser Speech processes audio; ClipAI does not retain audio or transcripts."
                ),
                justify="left",
                wraplength=385,
            ).pack(anchor="w", fill="x")
            buttons = ctk.CTkFrame(frame, fg_color="transparent")
            buttons.pack(side="bottom", fill="x", pady=(16, 0))
            ctk.CTkButton(buttons, text="Not now", command=self.close).pack(side="right")
            ctk.CTkButton(buttons, text="Enable Microphone", command=self._enable).pack(side="right", padx=(0, 8))
            self._dialog.protocol("WM_DELETE_WINDOW", self.close)
        self._dialog.deiconify()
        self._dialog.lift()
        self._dialog.focus_force()

    def close(self) -> None:
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.withdraw()

    def _enable(self) -> None:
        self._command_sink(EnableVoiceInput(VoiceSetupId(uuid.uuid4().hex)))
