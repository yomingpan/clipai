"""Small caret-free Voice Input surface; callbacks emit typed user intents."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from ClipAI.core.ports import NativeWindowSurface
from ClipAI.core.models import InlineInputMode, PasteOutcome
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
        on_copy: Callable[[], None] = lambda: None,
        native_window_surface: NativeWindowSurface | None = None,
        interaction_id: str = "",
        mode: InlineInputMode = "choice",
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
        self._mode = mode
        self._native_window_surface = native_window_surface
        self._wave = _VoiceWaveIndicator(self._window, lifecycle=self._lifecycle, font_family="Microsoft JhengHei")
        self._wave.pack(anchor="w")
        self._choice: tk.Frame | None = None
        self._choice_actions_enabled = False
        self.interaction_id = interaction_id
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._on_copy = on_copy
        self._copy_button: tk.Button | None = None
        self._copy_status: tk.Label | None = None
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
        if self._mode == "minimal":
            if self._native_window_surface is not None:
                self._native_window_surface.show_without_activation(self._window.winfo_id())
        else:
            self._window.lift()
            self._window.focus_force()

    def update(self, projection: VoiceProjection) -> None:
        if self._lifecycle.is_closed:
            return
        phase = projection.capture_phase
        finalizing = phase in {VoiceCapturePhase.STOP_REQUESTED, VoiceCapturePhase.FINALIZING, VoiceCapturePhase.CANCEL_REQUESTED}
        word = "取消中" if phase is VoiceCapturePhase.CANCEL_REQUESTED else "整理" if finalizing else "無聲" if projection.silence_detected else "聆聽" if phase is VoiceCapturePhase.LISTENING else "語音"
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

    def present_choice(self, text: str, allow_refine: bool = True, message: str = "") -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = True
        self._allow_refine = allow_refine
        if self._choice is not None:
            self._choice.destroy()
        self._copy_button = None
        self._copy_status = None
        frame = self._choice = tk.Frame(self._window, bg="#20272B")
        frame.pack(fill="x", pady=(8, 0))
        if message:
            tk.Label(frame, text=message, fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        self._add_readonly_text(frame, text)
        controls = tk.Frame(frame, bg="#20272B")
        controls.pack(fill="x")
        tk.Button(controls, text="貼上原文", command=lambda: self._confirm(False)).pack(side="left")
        if allow_refine:
            tk.Button(controls, text="潤飾後貼上", command=lambda: self._confirm(True)).pack(side="left")
        self._add_copy_control(controls)
        tk.Button(controls, text="丟棄", command=self._cancel).pack(side="right")
        shortcuts = "Enter 貼上原文    Ctrl+P 潤飾後貼上    Esc 取消" if allow_refine else "Enter 貼上原文    Esc 取消"
        tk.Label(frame, text=shortcuts, fg="white", bg="#20272B").pack(fill="x")
        tk.Label(frame, text="AI 幫你順稿，不替你改立場與用字選擇", fg="#B8C9C3", bg="#20272B").pack(fill="x")
        self._lifecycle.focus()

    def show_refining(self) -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = False
        if self._choice is not None:
            self._choice.destroy()
            self._choice = None
            self._copy_button = None
            self._copy_status = None
        self._wave.update_state(word="整理中", level=0, listening=False, silence=False, enabled=True, active=True, command=None)

    def show_refinement_pending(self) -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = False
        if self._choice is not None:
            self._choice.destroy()
            self._choice = None
            self._copy_button = None
            self._copy_status = None
        self._wave.update_state(word="準備潤飾", level=0, listening=False, silence=False, enabled=True, active=True, command=None)

    def show_cancel_unconfirmed(self, text: str) -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = False
        if self._choice is not None:
            self._choice.destroy()
        self._copy_button = None
        self._copy_status = None
        frame = self._choice = tk.Frame(self._window, bg="#20272B")
        frame.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text="取消尚未確認；不會送出貼上。可複製原文，或按 Esc 重試取消。", fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        self._add_readonly_text(frame, text)
        self._add_copy_control(frame)
        self._wave.update_state(word="取消待確認", level=0, listening=False, silence=False, enabled=True, active=False, command=None)
        self._lifecycle.focus()

    def show_paste_pending(self) -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = False
        if self._choice is not None:
            self._choice.destroy()
            self._choice = None
            self._copy_button = None
            self._copy_status = None
        self._wave.update_state(word="準備貼上", level=0, listening=False, silence=False, enabled=True, active=True, command=None)

    def show_paste_cancelling(self) -> None:
        if not self._lifecycle.is_closed:
            self._choice_actions_enabled = False
            self._wave.update_state(word="取消中", level=0, listening=False, silence=False, enabled=True, active=True, command=None)

    def show_paste_outcome(self, outcome: PasteOutcome, text: str) -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = False
        if self._choice is not None:
            self._choice.destroy()
        self._copy_button = None
        self._copy_status = None
        frame = self._choice = tk.Frame(self._window, bg="#20272B")
        frame.pack(fill="x", pady=(8, 0))
        messages = {
            "dispatched_unconfirmed": "已送出貼上快捷鍵；請確認原本的輸入欄位。",
            "failed": "尚未貼上。可複製下方內容，切回原欄位手動貼上。",
            "cancelled": "已取消，沒有送出貼上。",
            "cleanup_failed": "貼上或剪貼簿還原無法確認。請檢查原欄位與剪貼簿。",
        }
        tk.Label(frame, text=messages[outcome.state], fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        if outcome.state in {"failed", "cleanup_failed"}:
            self._add_readonly_text(frame, text)
            self._add_copy_control(frame)
            tk.Button(frame, text="關閉", command=self._cancel).pack(side="right")
            self._lifecycle.focus()
        self._wave.update_state(word="貼上結果", level=0, listening=False, silence=False, enabled=True, active=False, command=None)

    def show_recovery(self, text: str, message: str) -> None:
        if self._lifecycle.is_closed:
            return
        self._choice_actions_enabled = False
        if self._choice is not None:
            self._choice.destroy()
        self._copy_button = None
        self._copy_status = None
        frame = self._choice = tk.Frame(self._window, bg="#20272B")
        frame.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text=message, fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        self._add_readonly_text(frame, text)
        self._add_copy_control(frame)
        tk.Button(frame, text="丟棄", command=self._cancel).pack(side="right")
        self._lifecycle.focus()

    def show_copy_state(self, state: str) -> None:
        if self._lifecycle.is_closed or self._copy_button is None or self._copy_status is None:
            return
        self._copy_button.configure(state="disabled" if state == "pending" else "normal")
        messages = {"pending": "複製中…", "succeeded": "已複製", "failed": "複製失敗，請選取文字手動複製。"}
        self._copy_status.configure(text=messages[state])

    def _add_copy_control(self, parent: tk.Misc) -> None:
        self._copy_button = tk.Button(parent, text="複製", command=self._on_copy)
        self._copy_button.pack(side="left", anchor="w")
        self._copy_status = tk.Label(parent, text="", fg="white", bg="#20272B")
        self._copy_status.pack(side="left", anchor="w")

    @staticmethod
    def _add_readonly_text(parent: tk.Misc, text: str) -> tk.Text:
        content = tk.Frame(parent, bg="#20272B")
        content.pack(fill="both", expand=True)
        full_text = tk.Text(content, height=6, width=44, wrap="word", fg="white", bg="#20272B", relief="flat")
        full_text.insert("1.0", text)
        full_text.configure(state="disabled")
        full_text.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(content, command=full_text.yview)
        scrollbar.pack(side="right", fill="y")
        full_text.configure(yscrollcommand=scrollbar.set)
        return full_text

    def close(self, *, flash_failure: bool = False, message: str = "") -> None:
        if self._lifecycle.is_closed:
            return
        if flash_failure:
            self._wave.update_state(word="未完成", level=0, listening=False, silence=False, enabled=True, active=False, command=None)
            self._window.configure(bg="#A33B3B")
            if message:
                tk.Label(self._window, text=message, fg="white", bg="#A33B3B").pack()
            self._lifecycle.schedule(3000, self._lifecycle.close)
        else:
            self._lifecycle.close()

    def _confirm(self, refine: bool) -> str:
        if self._choice is not None and self._choice_actions_enabled and (not refine or self._allow_refine):
            self._on_confirm(refine)
        return "break"

    def _cancel(self) -> str:
        self._on_cancel()
        return "break"
