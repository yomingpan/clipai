"""Small caret-free Voice Input surface; callbacks emit typed user intents."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from ClipAI.core.ports import NativeWindowSurface
from ClipAI.core.voice import VoiceCapturePhase, VoiceProjection
from ClipAI.ui.base_dialog import _VoiceWaveIndicator
from ClipAI.ui.dialog_lifecycle import DialogLifecycle


class InlineDictationWindow:
    def __init__(
        self,
        root: tk.Misc,
        *,
        on_confirm: Callable[[bool], None],
        on_cancel: Callable[[], None],
        native_window_surface: NativeWindowSurface | None = None,
    ) -> None:
        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        try:
            self._window.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self._window.configure(bg="#20272B", padx=8, pady=8)
        self._lifecycle = DialogLifecycle(
            self._window,
            owns_mainloop=False,
            window_activator=(
                lambda window: native_window_surface.activate(window.winfo_id())
                if native_window_surface is not None
                else None
            ),
        )
        self._wave = _VoiceWaveIndicator(self._window, lifecycle=self._lifecycle, font_family="Microsoft JhengHei")
        self._wave.pack(anchor="w")
        self._choice: tk.Frame | None = None
        self.workflow_id = ""
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._window.bind("<Return>", lambda _event: self._confirm(False))
        self._window.bind("<KP_Enter>", lambda _event: self._confirm(False))
        self._window.bind("<Control-p>", lambda _event: self._confirm(True))
        self._window.bind("<Control-P>", lambda _event: self._confirm(True))
        self._window.bind("<Escape>", lambda _event: self._cancel())

    def show(self) -> None:
        if self._lifecycle.is_closed:
            return
        x, y = self._window.winfo_pointerxy()
        self._window.geometry(f"+{x + 14}+{y + 18}")
        self._window.deiconify()
        self._window.lift()
        self._window.focus_force()

    def update(self, projection: VoiceProjection) -> None:
        if self._lifecycle.is_closed:
            return
        if projection.workflow_id is not None:
            self.workflow_id = projection.workflow_id
        phase = projection.capture_phase
        finalizing = phase in {VoiceCapturePhase.STOP_REQUESTED, VoiceCapturePhase.FINALIZING, VoiceCapturePhase.CANCEL_REQUESTED}
        word = "整理" if finalizing else "無聲" if projection.silence_detected else "聆聽" if phase is VoiceCapturePhase.LISTENING else "語音"
        countdown = projection.remaining_seconds
        self._wave.update_state(
            word=word,
            level=projection.audio_level,
            listening=phase is VoiceCapturePhase.LISTENING,
            silence=projection.silence_detected,
            enabled=True,
            active=True,
            command=None,
            countdown_seconds=countdown if countdown is not None and countdown <= 30 and not finalizing else None,
        )
        self._window.configure(bg="#D9A441" if countdown is not None and countdown <= 30 and not finalizing else "#20272B")

    def present_choice(self, text: str) -> None:
        if self._lifecycle.is_closed:
            return
        if self._choice is not None:
            self._choice.destroy()
        frame = self._choice = tk.Frame(self._window, bg="#20272B")
        frame.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text=text[:160], anchor="w", justify="left", wraplength=340, fg="white", bg="#20272B").pack(fill="x")
        tk.Label(frame, text="Enter 貼上原文    Ctrl+P 潤飾後貼上    Esc 取消", fg="white", bg="#20272B").pack(fill="x")
        tk.Label(frame, text="AI 幫你順稿，不替你改立場與用字選擇", fg="#B8C9C3", bg="#20272B").pack(fill="x")
        self._lifecycle.focus()

    def show_refining(self) -> None:
        if self._lifecycle.is_closed:
            return
        if self._choice is not None:
            self._choice.destroy()
            self._choice = None
        self._wave.update_state(word="整理中", level=0, listening=False, silence=False, enabled=True, active=True, command=None)

    def close(self, *, flash_failure: bool = False, message: str = "") -> None:
        if self._lifecycle.is_closed:
            return
        if flash_failure:
            self._window.configure(bg="#A33B3B")
            if message:
                tk.Label(self._window, text=message, fg="white", bg="#A33B3B").pack()
            self._lifecycle.schedule(900, self._lifecycle.close)
        else:
            self._lifecycle.close()

    def _confirm(self, refine: bool) -> str:
        if self._choice is not None:
            if refine:
                self.show_refining()
            self._on_confirm(refine)
        return "break"

    def _cancel(self) -> str:
        self._on_cancel()
        return "break"
