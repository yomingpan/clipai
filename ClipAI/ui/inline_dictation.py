"""Small caret-free Voice Input surface; callbacks emit typed user intents."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import customtkinter as ctk
from customtkinter.windows.widgets.scaling import ScalingTracker

from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface
from ClipAI.core.models import DisplayMetrics, InlineDictationPlacement, InlineInputMode, PasteOutcome
from ClipAI.core.voice import VoiceCapturePhase, VoiceProjection
from ClipAI.ui.base_dialog import ACTION_COLOR, ACTION_HOVER_COLOR, TC_FONT_FAMILY, _VoiceWaveIndicator
from ClipAI.ui.dialog_lifecycle import DialogLifecycle


def _clamp_inline_position(metrics: DisplayMetrics, width: int, height: int) -> tuple[int, int]:
    return _resolve_inline_position(metrics, width, height, "cursor", (metrics.cursor_x, metrics.cursor_y))


def _resolve_inline_position(
    metrics: DisplayMetrics, width: int, height: int,
    placement: InlineDictationPlacement, anchor: tuple[int, int],
) -> tuple[int, int]:
    margin = 8
    left = metrics.work_x + margin
    top = metrics.work_y + margin
    right = max(left, metrics.work_x + metrics.work_width - width - margin)
    bottom = max(top, metrics.work_y + metrics.work_height - height - margin)
    if placement == "bottom_center":
        requested_x = metrics.work_x + (metrics.work_width - width) // 2
        requested_y = metrics.work_y + metrics.work_height - height - margin
    else:
        requested_x, requested_y = anchor[0] + 14, anchor[1] + 18
    return min(max(requested_x, left), right), min(max(requested_y, top), bottom)


class InlineDictationWindow:
    def __init__(
        self,
        root: tk.Misc,
        *,
        on_confirm: Callable[[bool], None],
        on_cancel: Callable[[], None],
        on_copy: Callable[[], None] = lambda: None,
        native_window_surface: NativeWindowSurface | None = None,
        display_metrics: DisplayMetricsReader | None = None,
        interaction_id: str = "",
        mode: InlineInputMode = "choice",
        placement: InlineDictationPlacement = "cursor",
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
                (lambda window: native_window_surface.activate(window.winfo_id()))
                if native_window_surface is not None else None
            ),
        )
        self._mode = mode
        self._placement = placement
        self._anchor: tuple[int, int] | None = None
        self._start_metrics: DisplayMetrics | None = None
        self._scaling_registered = False
        self._scale = 1.0
        self._labels: list[tuple[tk.Label, int | None]] = []
        self._text_widgets: list[tk.Text] = []
        self._native_window_surface = native_window_surface
        self._display_metrics = display_metrics
        self._wave = _VoiceWaveIndicator(self._window, lifecycle=self._lifecycle, font_family="Microsoft JhengHei")
        self._wave.pack(anchor="w")
        self._choice: tk.Frame | None = None
        self._choice_actions_enabled = False
        self.interaction_id = interaction_id
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._on_copy = on_copy
        self._copy_button: ctk.CTkButton | None = None
        self._copy_status: tk.Label | None = None
        self._window.bind("<Return>", lambda _event: self._confirm(False))
        self._window.bind("<KP_Enter>", lambda _event: self._confirm(False))
        self._window.bind("<Control-p>", lambda _event: self._confirm(True))
        self._window.bind("<Control-P>", lambda _event: self._confirm(True))
        self._window.bind("<Escape>", lambda _event: self._cancel())
        self._window.bind("<Destroy>", self._on_window_destroy, add="+")

    def _on_window_destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is self._window and self._scaling_registered:
            ScalingTracker.remove_window(self._set_scaling, self._window)
            self._scaling_registered = False

    def block_update_dimensions_event(self) -> None:
        return None

    def unblock_update_dimensions_event(self) -> None:
        return None

    def _set_scaling(self, widget_scaling: float, window_scaling: float) -> None:
        previous_scale = self._scale
        self._scale = max(0.1, widget_scaling)
        try:
            self._window.configure(padx=round(8 * self._scale), pady=round(8 * self._scale))
            for label, wraplength in self._labels:
                if label.winfo_exists():
                    label.configure(font=(TC_FONT_FAMILY, -max(1, round(11 * self._scale))))
                    if wraplength is not None:
                        label.configure(wraplength=round(wraplength * self._scale))
            for widget in self._text_widgets:
                if widget.winfo_exists():
                    widget.configure(font=(TC_FONT_FAMILY, -max(1, round(11 * self._scale))))
            self._wave.redraw()
            if self._anchor is not None and self._scale != previous_scale:
                self._window.after_idle(self._reclamp_fixed_anchor)
        except tk.TclError:
            return

    def _reclamp_fixed_anchor(self) -> None:
        if self._start_metrics is None or self._anchor is None:
            return
        try:
            self._window.update_idletasks()
            width, height = self._window.winfo_reqwidth(), self._window.winfo_reqheight()
            x, y = _resolve_inline_position(self._start_metrics, width, height, self._placement, self._anchor)
            self._window.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            return

    def _label(self, parent: tk.Misc, **options) -> tk.Label:
        wraplength = options.get("wraplength")
        label = tk.Label(parent, **options)
        self._labels.append((label, wraplength))
        self._set_scaling(self._scale, self._scale)
        return label

    def show(self) -> None:
        if self._lifecycle.is_closed:
            return
        self._place()
        self._window.deiconify()
        if self._mode == "minimal":
            if self._native_window_surface is not None:
                self._native_window_surface.show_without_activation(self._window.winfo_id())
        else:
            self._window.lift()
            self._window.focus_force()

    def _place(self) -> None:
        try:
            if self._start_metrics is None:
                if self._display_metrics is not None:
                    self._start_metrics = self._display_metrics.current()
                else:
                    pointer_x, pointer_y = self._window.winfo_pointerxy()
                    self._start_metrics = DisplayMetrics(1.0, 0, 0, self._window.winfo_screenwidth(), self._window.winfo_screenheight(), pointer_x, pointer_y)
                self._anchor = (self._start_metrics.cursor_x, self._start_metrics.cursor_y)
            metrics = self._start_metrics
            anchor = self._anchor
            assert anchor is not None
            self._window.update_idletasks()
            width, height = self._window.winfo_reqwidth(), self._window.winfo_reqheight()
            x, y = _resolve_inline_position(metrics, width, height, self._placement, anchor)
            self._window.geometry(f"{width}x{height}+{x}+{y}")
            self._window.update_idletasks()
            dpi = ScalingTracker.get_window_dpi_scaling(self._window)
            if not self._scaling_registered:
                setattr(self._window, "block_update_dimensions_event", self.block_update_dimensions_event)
                setattr(self._window, "unblock_update_dimensions_event", self.unblock_update_dimensions_event)
                ScalingTracker.add_window(self._set_scaling, self._window)
                self._scaling_registered = True
            ScalingTracker.window_dpi_scaling_dict[self._window] = dpi
            ScalingTracker.update_scaling_callbacks_for_window(self._window)
            self._window.update_idletasks()
            width, height = self._window.winfo_reqwidth(), self._window.winfo_reqheight()
            x, y = _resolve_inline_position(metrics, width, height, self._placement, anchor)
            self._window.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            return

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
            self._label(frame, text=message, fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        self._add_readonly_text(frame, text)
        controls = tk.Frame(frame, bg="#20272B")
        controls.pack(fill="x")
        self._action_button(controls, "貼上原文", lambda: self._confirm(False)).pack(side="left", padx=(0, 5))
        if allow_refine:
            self._action_button(controls, "潤飾後貼上", lambda: self._confirm(True)).pack(side="left", padx=(0, 5))
        self._add_copy_control(controls)
        self._action_button(controls, "丟棄", self._cancel).pack(side="right")
        shortcuts = "Enter 貼上原文    Ctrl+P 潤飾後貼上    Esc 取消" if allow_refine else "Enter 貼上原文    Esc 取消"
        self._label(frame, text=shortcuts, fg="white", bg="#20272B").pack(fill="x")
        self._label(frame, text="AI 幫你順稿，不替你改立場與用字選擇", fg="#B8C9C3", bg="#20272B").pack(fill="x")
        self._place()
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
        self._place()

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
        self._place()

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
        self._label(frame, text="取消尚未確認；不會送出貼上。可複製原文，或按 Esc 重試取消。", fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        self._add_readonly_text(frame, text)
        self._add_copy_control(frame)
        self._wave.update_state(word="取消待確認", level=0, listening=False, silence=False, enabled=True, active=False, command=None)
        self._place()
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
        self._place()

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
        self._label(frame, text=messages[outcome.state], fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        if outcome.state in {"failed", "cleanup_failed"}:
            self._add_readonly_text(frame, text)
            self._add_copy_control(frame)
            self._action_button(frame, "關閉", self._cancel).pack(side="right")
            self._lifecycle.focus()
        self._wave.update_state(word="貼上結果", level=0, listening=False, silence=False, enabled=True, active=False, command=None)
        self._place()

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
        self._label(frame, text=message, fg="white", bg="#20272B", wraplength=340, justify="left").pack(fill="x")
        self._add_readonly_text(frame, text)
        self._add_copy_control(frame)
        self._action_button(frame, "丟棄", self._cancel).pack(side="right")
        self._place()
        self._lifecycle.focus()

    def show_copy_state(self, state: str) -> None:
        if self._lifecycle.is_closed or self._copy_button is None or self._copy_status is None:
            return
        self._copy_button.configure(state="disabled" if state == "pending" else "normal")
        messages = {"pending": "複製中…", "succeeded": "已複製", "failed": "複製失敗，請選取文字手動複製。"}
        self._copy_status.configure(text=messages[state])
        self._place()

    def _add_copy_control(self, parent: tk.Misc) -> None:
        self._copy_button = self._action_button(parent, "複製", self._on_copy)
        self._copy_button.pack(side="left", anchor="w", padx=(0, 5))
        self._copy_status = self._label(parent, text="", fg="white", bg="#20272B")
        self._copy_status.pack(side="left", anchor="w")

    @staticmethod
    def _action_button(parent: tk.Misc, label: str, command: Callable[[], object]) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=label, command=command, width=76, height=24,
            corner_radius=6, fg_color=ACTION_COLOR, hover_color=ACTION_HOVER_COLOR,
            text_color="white", font=ctk.CTkFont(family=TC_FONT_FAMILY, size=10),
        )

    def _add_readonly_text(self, parent: tk.Misc, text: str) -> tk.Text:
        content = tk.Frame(parent, bg="#20272B")
        content.pack(fill="both", expand=True)
        full_text = tk.Text(content, height=6, width=44, wrap="word", fg="white", bg="#20272B", relief="flat")
        full_text.insert("1.0", text)
        full_text.configure(state="disabled")
        full_text.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(content, command=full_text.yview)
        scrollbar.pack(side="right", fill="y")
        full_text.configure(yscrollcommand=scrollbar.set)
        self._text_widgets.append(full_text)
        self._set_scaling(self._scale, self._scale)
        return full_text

    def close(self, *, flash_failure: bool = False, message: str = "") -> None:
        if self._lifecycle.is_closed:
            return
        if flash_failure:
            self._wave.update_state(word="未完成", level=0, listening=False, silence=False, enabled=True, active=False, command=None)
            self._window.configure(bg="#A33B3B")
            if message:
                self._label(self._window, text=message, fg="white", bg="#A33B3B").pack()
            self._place()
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
