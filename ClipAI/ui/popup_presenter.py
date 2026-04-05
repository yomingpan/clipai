from __future__ import annotations

import queue
import re
import threading
import time
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from clipai.core.constants import EVENT_TTS_STATE
from clipai.core.event_bus import get_event_bus
from clipai.platform.clipboard import write_clipboard_text
from clipai.services.archive_service import ArchiveService
from clipai.services.popup_session import PopupSession
from clipai.ui.tooltip import attach_tooltip

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

POPUP_BORDER_COLOR = "#0F3D78"
POPUP_TITLE_COLOR = "#4F89D9"
SUCCESS_COLOR = "#2E9E5B"
ERROR_COLOR = "#D64545"
STOP_COLOR = "#C84C4C"
POPUP_MASK_COLOR = "#010203"
CHUNK_FLUSH_MS = 40
POPUP_WIDTH_RATIO = 0.20
POPUP_HEIGHT_RATIO = 0.27
POPUP_MIN_WIDTH = 320
POPUP_MAX_WIDTH = 430
POPUP_MIN_HEIGHT = 220
POPUP_MAX_HEIGHT = 290
ELLIPSIS = "..."
ICON_SPEAK = "\U0001F50A"
ICON_COPY = "\u29C9"
ICON_ARCHIVE = "\u21A7"
ICON_PIN = "\U0001F4CC"
ICON_STOP = "\u25A0"
ICON_CHECK = "\u2713"
ICON_ERROR = "!"
CLOSE_GRACE_SEC = 1.2


class PopupPresenter:
    def __init__(self, on_follow_up: Callable[[PopupSession, str], None] | None = None, tts_service=None) -> None:
        self._archive_service = ArchiveService()
        self._on_follow_up = on_follow_up
        self._tts_service = tts_service
        self._jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root: ctk.CTk | None = None
        self._active_window = None
        self._active_session: PopupSession | None = None
        self._text_widget: tk.Text | None = None
        self._follow_entry = None
        self._follow_hint_label = None
        self._follow_frame = None
        self._follow_visible = False
        self._secondary_row = None
        self._secondary_visible = False
        self._input_label = None
        self._pin_button = None
        self._main_frame = None
        self._title_label = None
        self._is_pinned = False
        self._ready = threading.Event()
        self._chunk_flush_scheduled = False
        self._pending_chunks: list[str] = []
        self._button_refs: dict[str, ctk.CTkButton] = {}
        self._close_suppressed_until = 0.0
        get_event_bus().subscribe(EVENT_TTS_STATE, self._handle_tts_state)

    @staticmethod
    def _format_input_preview(text: str, max_chars: int = 88) -> str:
        compact = " ".join((text or "").split())
        if not compact:
            return "Analysis: (empty input)"
        if len(compact) > max_chars:
            compact = compact[: max_chars - 3].rstrip() + "..."
        return f"Analysis: {compact}"

    @staticmethod
    def _speak_phase_to_ui_state(phase: str, is_speaking: bool) -> bool | None:
        normalized = (phase or "").strip().lower()
        if normalized == "start":
            return True
        if normalized in {"stop", "end", "error"}:
            return False
        if is_speaking:
            return True
        return None

    def show_session(self, session: PopupSession) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._show_session_on_ui(session))

    def update_input(self, session_id: str, original_input: str) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._update_input_on_ui(session_id, original_input))

    def append_chunk(self, session_id: str, chunk: str) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._append_chunk_on_ui(session_id, chunk))

    def finalize_result(self, session_id: str, content: str) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._finalize_result_on_ui(session_id, content))

    def flash_status(self, session_id: str, status: str) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._flash_status_on_ui(session_id, status))

    def refresh_session(self, session_id: str) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._refresh_session_on_ui(session_id))

    def set_follow_up_enabled(self, session_id: str, enabled: bool) -> None:
        self._ensure_ui_thread()
        self._jobs.put(lambda: self._set_follow_up_enabled_on_ui(session_id, enabled))

    def _handle_tts_state(self, payload: dict) -> None:
        self._ensure_ui_thread()
        phase = str(payload.get("phase") or "")
        is_speaking = bool(payload.get("is_speaking"))
        self._jobs.put(lambda: self._apply_tts_state_on_ui(phase, is_speaking))

    def _apply_tts_state_on_ui(self, phase: str, is_speaking: bool) -> None:
        ui_state = self._speak_phase_to_ui_state(phase, is_speaking)
        if phase.strip().lower() in {"start", "stop", "end", "error"}:
            self._suppress_auto_close()
        if ui_state is not None:
            self._set_speak_button_state_on_ui(ui_state)
        if phase.strip().lower() in {"end", "stop", "error"}:
            self._refocus_popup()

    def _ensure_ui_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._ui_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _ui_loop(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        self._root = root
        self._ready.set()

        def _pump() -> None:
            while True:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                try:
                    job()
                except Exception:
                    pass
            root.after(30, _pump)

        root.after(30, _pump)
        root.mainloop()

    def _show_session_on_ui(self, session: PopupSession) -> None:
        if self._root is None:
            return
        self._destroy_active_window()

        root = self._root
        window = ctk.CTkToplevel(root)
        self._active_window = window
        self._active_session = session
        window.title(f"ClipAI - {session.action_name}")
        window.configure(fg_color=POPUP_MASK_COLOR)
        window.overrideredirect(True)
        try:
            window.wm_attributes("-transparentcolor", POPUP_MASK_COLOR)
        except tk.TclError:
            pass

        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = max(POPUP_MIN_WIDTH, min(POPUP_MAX_WIDTH, int(screen_w * POPUP_WIDTH_RATIO)))
        height = max(POPUP_MIN_HEIGHT, min(POPUP_MAX_HEIGHT, int(screen_h * POPUP_HEIGHT_RATIO)))
        pointer_x = window.winfo_pointerx()
        pointer_y = window.winfo_pointery()
        x = min(pointer_x + 18, screen_w - width - 16)
        y = min(pointer_y + 18, screen_h - height - 24)
        x = max(16, x)
        y = max(16, y)
        window.geometry(f"{width}x{height}+{x}+{y}")

        main_frame = ctk.CTkFrame(
            window,
            fg_color=("white", "#181B22"),
            corner_radius=18,
            border_width=3,
            border_color=POPUP_BORDER_COLOR,
            bg_color="transparent",
        )
        main_frame.pack(fill="both", expand=True, padx=1, pady=1)
        self._main_frame = main_frame

        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=32)
        header_frame.pack(fill="x", padx=10, pady=(8, 4))
        header_frame.pack_propagate(False)

        title_label = ctk.CTkLabel(
            header_frame,
            text=f"ClipAI - {session.action_name}",
            font=("Microsoft JhengHei", 11, "bold"),
            text_color=POPUP_TITLE_COLOR,
            anchor="w",
        )
        title_label.pack(side="left", fill="y")
        self._title_label = title_label

        action_bar = ctk.CTkFrame(header_frame, fg_color="transparent")
        action_bar.pack(side="right")

        def _header_button(name: str, text: str, tooltip: str, command, *, width: int = 26) -> ctk.CTkButton:
            button = ctk.CTkButton(
                action_bar,
                text=text,
                width=width,
                height=24,
                corner_radius=8,
                font=("Segoe UI Symbol", 10, "bold"),
                fg_color="transparent",
                hover_color=("#E8EEF5", "#232A35"),
                border_width=1,
                border_color=("#D8DEE8", "#2B3240"),
                text_color=("gray10", "#DCE4EE"),
                command=command,
            )
            button.pack(side="left", padx=(4, 0))
            attach_tooltip(button, tooltip)
            self._button_refs[name] = button
            return button

        def _toggle_pin() -> None:
            self._is_pinned = not self._is_pinned
            if self._pin_button is not None:
                self._pin_button.configure(
                    fg_color=(POPUP_TITLE_COLOR if self._is_pinned else "transparent"),
                    text_color=("white" if self._is_pinned else ("gray10", "#DCE4EE")),
                )

        drag_state = {"x": 0, "y": 0}

        def _start_drag(event) -> None:
            drag_state["x"] = event.x_root - window.winfo_x()
            drag_state["y"] = event.y_root - window.winfo_y()

        def _drag_window(event) -> None:
            x = max(0, event.x_root - drag_state["x"])
            y = max(0, event.y_root - drag_state["y"])
            window.geometry(f"+{x}+{y}")

        for widget in (header_frame, title_label):
            widget.bind("<ButtonPress-1>", _start_drag, add="+")
            widget.bind("<B1-Motion>", _drag_window, add="+")

        _header_button("speak", ICON_SPEAK, "Speak / Stop", lambda: self._toggle_speak(session))
        _header_button("copy", ICON_COPY, "Copy", lambda: self._copy_current_output(session))
        _header_button("archive", ICON_ARCHIVE, "Archive", lambda: self._archive_current_output(session))
        _header_button("overflow", ELLIPSIS, "More actions", self._toggle_secondary_actions_on_ui, width=28)
        self._pin_button = _header_button("pin", ICON_PIN, "Pin", _toggle_pin)

        secondary_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        self._secondary_row = secondary_row
        for label in ("Deep", "Refine"):
            button = ctk.CTkButton(
                secondary_row,
                text=label,
                width=68,
                height=24,
                corner_radius=8,
                font=("Microsoft JhengHei", 10, "bold"),
                fg_color="transparent",
                hover_color=("#E8EEF5", "#232A35"),
                border_width=1,
                border_color=("#D8DEE8", "#2B3240"),
                text_color=("gray10", "#DCE4EE"),
                command=lambda text=label: self._flash_secondary_action(text),
            )
            button.pack(side="left", padx=(0, 6))

        follow_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self._follow_frame = follow_frame

        follow_entry = ctk.CTkEntry(
            follow_frame,
            placeholder_text=f"Follow-up ({session.round_count}/{session.max_rounds})",
            font=("Microsoft JhengHei", 10),
            height=26,
        )
        follow_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._follow_entry = follow_entry

        follow_hint = ctk.CTkLabel(
            follow_frame,
            text=f"{session.round_count}/{session.max_rounds}",
            font=("Microsoft JhengHei", 10),
            text_color=("gray45", "gray60"),
        )
        follow_hint.pack(side="right")
        self._follow_hint_label = follow_hint
        self._sync_follow_up_controls(session)

        input_value = ctk.CTkLabel(
            main_frame,
            text=self._format_input_preview(session.original_input),
            font=("Microsoft JhengHei", 9),
            text_color=("gray52", "gray58"),
            justify="left",
            anchor="w",
        )
        input_value.pack(fill="x", padx=10, pady=(0, 4))
        self._input_label = input_value

        text_container = ctk.CTkFrame(
            main_frame,
            corner_radius=10,
            border_width=1,
            border_color=("#D8DEE8", "#2B3240"),
            fg_color=("#FCFCFD", "#141922"),
        )
        text_container.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        text_widget = tk.Text(
            text_container,
            font=("Microsoft JhengHei", 10),
            wrap="word",
            padx=10,
            pady=8,
            borderwidth=0,
            highlightthickness=0,
            bg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]),
            fg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
            insertbackground=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
        )
        text_widget.pack(fill="both", expand=True, padx=2, pady=2)
        self._text_widget = text_widget
        self._render_session_text(text_widget, session)

        def _submit_follow_up(event=None) -> str | None:
            del event
            if self._active_session is None or self._active_session.session_id != session.session_id:
                return "break"
            if self._on_follow_up is None:
                return "break"
            prompt_text = follow_entry.get().strip()
            if not prompt_text:
                return "break"
            if not session.can_continue():
                self._sync_follow_up_controls(session)
                return "break"
            follow_entry.delete(0, "end")
            self._follow_visible = False
            self._follow_frame.pack_forget()
            self._set_follow_up_enabled_on_ui(session.session_id, False)
            if self._text_widget is not None:
                self._text_widget.focus_set()
            self._on_follow_up(session, prompt_text)
            return "break"

        follow_entry.bind("<Return>", _submit_follow_up)

        def _close(event=None) -> None:
            del event
            if self._tts_service is not None and self._tts_service.is_speaking():
                self._tts_service.stop()
            self._destroy_active_window(window)

        def _close_if_focus_left() -> None:
            if not window.winfo_exists():
                return
            if self._is_pinned:
                return
            if time.monotonic() < self._close_suppressed_until:
                return
            if self._tts_service is not None and self._tts_service.is_speaking():
                return
            try:
                focused = window.focus_get()
            except tk.TclError:
                focused = None

            if focused is None:
                _close()
                return

            try:
                same_popup = focused.winfo_toplevel() == window
            except tk.TclError:
                same_popup = False

            if not same_popup:
                _close()

        def _schedule_focus_check(event=None) -> None:
            del event
            if window.winfo_exists():
                window.after(180, _close_if_focus_left)

        self._bind_popup_shortcuts(window, session, _close)

        window.protocol("WM_DELETE_WINDOW", _close)
        window.bind("<FocusOut>", _schedule_focus_check)
        window.after(60, lambda: window.focus_force())
        window.after(100, lambda: text_widget.focus_set())
        window.lift()
        window.attributes("-topmost", True)
        self._set_speak_button_state_on_ui(self._tts_service.is_speaking() if self._tts_service else False)

    def _destroy_active_window(self, window=None) -> None:
        target = window or self._active_window
        if target is not None:
            try:
                target.destroy()
            except Exception:
                pass
        self._active_window = None
        self._active_session = None
        self._text_widget = None
        self._follow_entry = None
        self._follow_hint_label = None
        self._follow_frame = None
        self._follow_visible = False
        self._secondary_row = None
        self._secondary_visible = False
        self._input_label = None
        self._pin_button = None
        self._main_frame = None
        self._title_label = None
        self._button_refs = {}
        self._pending_chunks = []
        self._chunk_flush_scheduled = False
        self._is_pinned = False
        self._close_suppressed_until = 0.0

    def _suppress_auto_close(self, seconds: float = CLOSE_GRACE_SEC) -> None:
        self._close_suppressed_until = max(self._close_suppressed_until, time.monotonic() + seconds)

    def _refocus_popup(self) -> None:
        if self._active_window is None or not self._active_window.winfo_exists():
            return
        self._active_window.after(50, lambda: self._active_window and self._active_window.winfo_exists() and self._active_window.focus_force())
        if self._text_widget is not None and self._text_widget.winfo_exists():
            self._active_window.after(90, lambda: self._text_widget and self._text_widget.winfo_exists() and self._text_widget.focus_set())

    def _bind_popup_shortcuts(self, window, session: PopupSession, close_cb) -> None:
        window.bind("<Escape>", close_cb)
        window.bind("<Control-c>", lambda event: self._copy_shortcut(event, session))
        window.bind("<Control-s>", lambda event: self._archive_shortcut(event, session))
        window.bind("<Control-slash>", self._toggle_follow_up_shortcut)
        window.bind("<Control-question>", self._toggle_follow_up_shortcut)
        window.bind("<Alt-Shift-Q>", lambda event: self._speak_shortcut(event, session))
        window.bind("<Alt-Shift-q>", lambda event: self._speak_shortcut(event, session))

    def _copy_shortcut(self, event, session: PopupSession) -> str:
        del event
        self._copy_current_output(session)
        return "break"

    def _archive_shortcut(self, event, session: PopupSession) -> str:
        del event
        self._archive_current_output(session)
        return "break"

    def _toggle_follow_up_shortcut(self, event) -> str:
        del event
        self._toggle_follow_up_on_ui()
        return "break"

    def _speak_shortcut(self, event, session: PopupSession) -> str:
        del event
        self._toggle_speak(session)
        return "break"

    def _toggle_follow_up_on_ui(self) -> None:
        if self._follow_frame is None or self._active_window is None or not self._active_window.winfo_exists():
            return
        self._follow_visible = not self._follow_visible
        if self._follow_visible:
            self._clear_follow_up_entry_on_ui()
            self._follow_frame.pack(fill="x", padx=10, pady=(0, 4), before=self._input_label)
            if self._follow_entry is not None:
                self._follow_entry.focus_set()
        else:
            self._follow_frame.pack_forget()
            if self._text_widget is not None:
                self._text_widget.focus_set()

    def _toggle_secondary_actions_on_ui(self) -> None:
        if self._secondary_row is None or self._input_label is None:
            return
        self._secondary_visible = not self._secondary_visible
        if self._secondary_visible:
            self._secondary_row.pack(fill="x", padx=10, pady=(0, 4), before=self._input_label)
        else:
            self._secondary_row.pack_forget()

    def _flash_secondary_action(self, label: str) -> None:
        if self._active_session is not None:
            self._flash_status_on_ui(self._active_session.session_id, "success")
        button = self._button_refs.get("overflow")
        if button is not None:
            self._pulse_button(button, label, SUCCESS_COLOR)

    def _update_input_on_ui(self, session_id: str, original_input: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._active_session.original_input = original_input
        if self._input_label is not None:
            self._input_label.configure(text=self._format_input_preview(original_input))

    def _refresh_session_on_ui(self, session_id: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._pending_chunks = []
        self._chunk_flush_scheduled = False
        if self._text_widget is not None:
            self._render_session_text(self._text_widget, self._active_session)
        self._clear_follow_up_entry_on_ui()
        self._sync_follow_up_controls(self._active_session)

    def _set_follow_up_enabled_on_ui(self, session_id: str, enabled: bool) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._follow_entry is None:
            return
        state = "normal" if enabled and self._active_session.can_continue() else "disabled"
        self._follow_entry.configure(state=state)
        if enabled:
            self._clear_follow_up_entry_on_ui()
            if self._text_widget is not None:
                self._text_widget.focus_set()

    def _append_chunk_on_ui(self, session_id: str, chunk: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._active_session.latest_result.strip() == "Connecting...":
            self._active_session.latest_result = ""
        self._active_session.latest_result += chunk
        self._pending_chunks.append(chunk)
        if self._chunk_flush_scheduled or self._active_window is None:
            return
        self._chunk_flush_scheduled = True
        self._active_window.after(CHUNK_FLUSH_MS, lambda sid=session_id: self._flush_pending_chunks_on_ui(sid))

    def _flush_pending_chunks_on_ui(self, session_id: str) -> None:
        self._chunk_flush_scheduled = False
        if self._active_session is None or self._active_session.session_id != session_id:
            self._pending_chunks = []
            return
        if self._text_widget is None or not self._pending_chunks:
            return
        chunk = "".join(self._pending_chunks)
        self._pending_chunks = []
        text_widget = self._text_widget
        try:
            autoscroll = float(text_widget.yview()[1]) >= 0.98
        except Exception:
            autoscroll = True
        text_widget.config(state="normal")
        if text_widget.get("1.0", "end-1c").strip() == "Connecting...":
            text_widget.delete("1.0", "end")
        text_widget.insert("end", chunk, ("body",))
        if autoscroll:
            text_widget.see("end")
        text_widget.config(state="disabled")

    def _finalize_result_on_ui(self, session_id: str, content: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._active_session.latest_result = content
        self._pending_chunks = []
        self._chunk_flush_scheduled = False
        if self._text_widget is not None:
            self._render_session_text(self._text_widget, self._active_session)
        self._sync_follow_up_controls(self._active_session)

    def _flash_status_on_ui(self, session_id: str, status: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._active_window is None or not self._active_window.winfo_exists():
            return

        if status == "success":
            color = SUCCESS_COLOR
            duration_ms = 1000
        elif status == "error":
            color = ERROR_COLOR
            duration_ms = 3000
        else:
            color = BRAND_COLOR
            color = POPUP_BORDER_COLOR
            duration_ms = 0

        self._apply_status_color(color)
        if duration_ms > 0:
            self._active_window.after(
                duration_ms,
                lambda: self._active_window
                and self._active_window.winfo_exists()
                and self._apply_status_color(POPUP_BORDER_COLOR),
            )

    def _apply_status_color(self, color: str) -> None:
        if self._main_frame is not None:
            self._main_frame.configure(border_color=color)

    def _sync_follow_up_controls(self, session: PopupSession) -> None:
        if self._follow_hint_label is not None:
            self._follow_hint_label.configure(text=f"{session.round_count}/{session.max_rounds}")
        if self._follow_entry is not None:
            if session.can_continue():
                self._follow_entry.configure(
                    state="normal",
                    placeholder_text=f"Follow-up ({session.round_count}/{session.max_rounds})",
                )
            else:
                self._follow_entry.configure(
                    state="disabled",
                    placeholder_text="Popup follow-up limit reached",
                )

    def _clear_follow_up_entry_on_ui(self) -> None:
        if self._follow_entry is None:
            return
        try:
            current_state = str(self._follow_entry.cget("state"))
        except Exception:
            current_state = "normal"
        if current_state == "disabled":
            self._follow_entry.configure(state="normal")
            self._follow_entry.delete(0, "end")
            self._follow_entry.configure(state="disabled")
            return
        self._follow_entry.delete(0, "end")

    @staticmethod
    def _render_session_text(text_widget: tk.Text, session: PopupSession) -> None:
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.tag_configure("body", spacing1=2, spacing3=3)
        text_widget.tag_configure("history", foreground="#7A7F87")
        text_widget.tag_configure("md_h1", font=("Microsoft JhengHei", 14, "bold"), spacing1=6, spacing3=4)
        text_widget.tag_configure("md_h2", font=("Microsoft JhengHei", 13, "bold"), spacing1=5, spacing3=3)
        text_widget.tag_configure("md_bold", font=("Microsoft JhengHei", 10, "bold"))
        text_widget.tag_configure("md_code", font=("Consolas", 9), background="#EEF3F8")
        PopupPresenter._insert_markdown(text_widget, session.latest_result.strip() or " ", base_tag="body")
        if session.rounds:
            for item in session.rounds:
                text_widget.insert("end", f"\n\n--- round {item.round_index} ---\n", ("history",))
                label = "Deep Think" if item.kind == "deep_think" else "Follow-up"
                text_widget.insert("end", f"{label}: {item.prompt_text.strip()}\n", ("history",))
                PopupPresenter._insert_markdown(text_widget, item.result_text.strip(), base_tag="history")
        text_widget.config(state="disabled")

    @staticmethod
    def _insert_markdown(text_widget: tk.Text, content: str, base_tag: str = "body") -> None:
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line:
                text_widget.insert("end", "\n", (base_tag,))
                continue

            if line.startswith("# "):
                PopupPresenter._insert_inline_markdown(text_widget, line[2:], ("md_h1",))
                text_widget.insert("end", "\n")
                continue
            if line.startswith("## "):
                PopupPresenter._insert_inline_markdown(text_widget, line[3:], ("md_h2",))
                text_widget.insert("end", "\n")
                continue
            if re.match(r"^(\-|\*|\d+\.)\s+", line):
                normalized = re.sub(r"^(\-|\*|\d+\.)\s+", "- ", line, count=1)
                PopupPresenter._insert_inline_markdown(text_widget, normalized, (base_tag,))
                text_widget.insert("end", "\n")
                continue

            PopupPresenter._insert_inline_markdown(text_widget, line, (base_tag,))
            text_widget.insert("end", "\n")

    @staticmethod
    def _insert_inline_markdown(text_widget: tk.Text, line: str, base_tags: tuple[str, ...]) -> None:
        pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
        cursor = 0
        for match in pattern.finditer(line):
            if match.start() > cursor:
                text_widget.insert("end", line[cursor:match.start()], base_tags)
            token = match.group(0)
            if token.startswith("**") and token.endswith("**"):
                text_widget.insert("end", token[2:-2], base_tags + ("md_bold",))
            elif token.startswith("`") and token.endswith("`"):
                text_widget.insert("end", token[1:-1], base_tags + ("md_code",))
            cursor = match.end()
        if cursor < len(line):
            text_widget.insert("end", line[cursor:], base_tags)

    @staticmethod
    def _copy_selection_or_full(text_widget: tk.Text | None, session: PopupSession) -> str:
        if text_widget is not None:
            try:
                selection = text_widget.get("sel.first", "sel.last").strip()
            except tk.TclError:
                selection = ""
            if selection:
                return selection
        return session.render_full_text()

    def _copy_current_output(self, session: PopupSession) -> None:
        try:
            self._suppress_auto_close()
            payload = self._copy_selection_or_full(self._text_widget, session)
            write_clipboard_text(payload)
            button = self._button_refs.get("copy")
            if button is not None:
                self._pulse_button(button, ICON_CHECK, SUCCESS_COLOR)
        except Exception:
            button = self._button_refs.get("copy")
            if button is not None:
                self._pulse_button(button, ICON_ERROR, ERROR_COLOR)

    def _archive_current_output(self, session: PopupSession) -> None:
        try:
            self._suppress_auto_close()
            self._archive_service.append_session(session)
            button = self._button_refs.get("archive")
            if button is not None:
                self._pulse_button(button, ICON_CHECK, SUCCESS_COLOR)
        except Exception:
            button = self._button_refs.get("archive")
            if button is not None:
                self._pulse_button(button, ICON_ERROR, ERROR_COLOR)

    def _toggle_speak(self, session: PopupSession) -> None:
        if self._tts_service is None:
            return
        self._suppress_auto_close()
        content = session.latest_result or session.render_full_text()
        if self._tts_service.is_speaking():
            self._tts_service.stop()
            self._set_speak_button_state_on_ui(False)
            self._refocus_popup()
            return
        self._set_speak_button_state_on_ui(True)
        self._tts_service.speak_async(content)

    def _set_speak_button_state_on_ui(self, is_speaking: bool) -> None:
        button = self._button_refs.get("speak")
        if button is None:
            return
        if is_speaking:
            button.configure(
                text=ICON_STOP,
                fg_color=STOP_COLOR,
                hover_color="#A93B3B",
                border_width=0,
                text_color="white",
            )
            return
        button.configure(
            text=ICON_SPEAK,
            fg_color="transparent",
            hover_color=("#E8EEF5", "#232A35"),
            border_width=1,
            border_color=("#D8DEE8", "#2B3240"),
            text_color=("gray10", "#DCE4EE"),
        )

    @staticmethod
    def _pulse_button(button: ctk.CTkButton, text: str, color: str, duration_ms: int = 1000) -> None:
        original = {
            "text": button.cget("text"),
            "fg_color": button.cget("fg_color"),
            "hover_color": button.cget("hover_color"),
            "border_width": button.cget("border_width"),
            "border_color": button.cget("border_color"),
            "text_color": button.cget("text_color"),
        }
        button.configure(text=text, fg_color=color, hover_color=color, border_width=0, text_color="white")
        button.after(
            duration_ms,
            lambda: button.winfo_exists()
            and button.configure(
                text=original["text"],
                fg_color=original["fg_color"],
                hover_color=original["hover_color"],
                border_width=original["border_width"],
                border_color=original["border_color"],
                text_color=original["text_color"],
            ),
        )
