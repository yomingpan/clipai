from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from clipai.core.constants import EVENT_TTS_STATE
from clipai.core.event_bus import EventBus, get_event_bus
from clipai.services.popup_session import PopupSession
from clipai.ui.tooltip import attach_tooltip
from clipai.ui.result_popup.action_handler import PopupActionHandler
from clipai.ui.result_popup.markdown_renderer import PopupMarkdownRenderer

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

POPUP_BORDER_COLOR = "#3A4454"
POPUP_TITLE_COLOR = "#4F89D9"
SUCCESS_COLOR = "#2E9E5B"
ERROR_COLOR = "#D64545"
STOP_COLOR = "#C84C4C"
POPUP_MASK_COLOR = "#010203"
BUTTON_ACCENT_BG = ("#E8F0FF", "#24415F")
BUTTON_ACCENT_HOVER = ("#D6E6FF", "#2D4B6B")
SELECTION_BG_COLOR = "#2A4E7A"
SELECTION_FG_COLOR = "#F7FAFF"
CHUNK_FLUSH_MS = 40
POPUP_WIDTH_RATIO = 0.20
POPUP_HEIGHT_RATIO = 0.27
POPUP_MIN_WIDTH = 320
POPUP_MAX_WIDTH = 430
POPUP_MIN_HEIGHT = 220
POPUP_MAX_HEIGHT = 290
ELLIPSIS = "..."
ICON_SPEAK = "\U0001F50A"
ICON_COPY = "\U0001F4CB"
ICON_ARCHIVE = "\U0001F4E6"
ICON_PIN = "\U0001F4CC"
ICON_STOP = "\u25A0"
ICON_CHECK = "\u2713"
ICON_ERROR = "!"
CLOSE_GRACE_SEC = 0.35

logger = logging.getLogger("clipai.ui.popup_presenter")


class PopupPresenter:
    def __init__(
        self,
        on_follow_up: Callable[[PopupSession, str], None] | None = None,
        *,
        on_session_closed: Callable[[str], None] | None = None,
        tts_service=None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._on_follow_up = on_follow_up
        self._on_session_closed = on_session_closed
        self._event_bus = event_bus or get_event_bus()
        self._action_handler = PopupActionHandler(tts_service=tts_service)
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
        self._meta_row = None
        self._pin_button = None
        self._main_frame = None
        self._title_label = None
        self._source_label = None
        self._is_pinned = False
        self._ready = threading.Event()
        self._chunk_flush_scheduled = False
        self._pending_chunks: list[str] = []
        self._button_refs: dict[str, ctk.CTkButton] = {}
        self._close_suppressed_until = 0.0
        self._shutdown_requested = False
        self._disposed = False
        self._tts_subscription_id = self._event_bus.subscribe(EVENT_TTS_STATE, self._handle_tts_state)

    @staticmethod
    def _format_input_preview(text: str, max_chars: int = 58) -> str:
        return PopupMarkdownRenderer.format_input_preview(text, max_chars=max_chars)

    @staticmethod
    def _input_preview_for_session(session: PopupSession) -> str:
        return PopupMarkdownRenderer.input_preview_for_session(session)

    @staticmethod
    def _result_text_for_session(session: PopupSession) -> str:
        return PopupMarkdownRenderer.result_text_for_session(session)

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
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._show_session_on_ui(session))

    def get_active_session_id(self) -> str | None:
        session = self._active_session
        if session is None:
            return None
        if self._active_window is None:
            return None
        try:
            if not self._active_window.winfo_exists():
                return None
        except tk.TclError:
            return None
        return session.session_id

    def is_session_active(self, session_id: str) -> bool:
        active_session_id = self.get_active_session_id()
        return active_session_id == session_id

    def update_input(self, session_id: str, original_input: str) -> None:
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._update_input_on_ui(session_id, original_input))

    def append_chunk(self, session_id: str, chunk: str) -> None:
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._append_chunk_on_ui(session_id, chunk))

    def finalize_result(self, session_id: str, content: str) -> None:
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._finalize_result_on_ui(session_id, content))

    def flash_status(self, session_id: str, status: str) -> None:
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._flash_status_on_ui(session_id, status))

    def refresh_session(self, session_id: str) -> None:
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._refresh_session_on_ui(session_id))

    def set_follow_up_enabled(self, session_id: str, enabled: bool) -> None:
        if self._disposed:
            return
        self._ensure_ui_thread()
        if self._disposed:
            return
        self._jobs.put(lambda: self._set_follow_up_enabled_on_ui(session_id, enabled))

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._shutdown_requested = True
        if self._tts_subscription_id is not None:
            self._event_bus.unsubscribe(self._tts_subscription_id)
            self._tts_subscription_id = None
        if self._thread is None and self._root is None:
            return

        closed = threading.Event()

        def _shutdown() -> None:
            try:
                self._destroy_active_window()
                if self._root is not None:
                    try:
                        self._root.quit()
                    except Exception:
                        logger.exception("Popup root quit failed.")
                    try:
                        self._root.destroy()
                    except Exception:
                        logger.exception("Popup root destroy failed.")
                    self._root = None
            finally:
                closed.set()

        self._jobs.put(_shutdown)
        closed.wait(timeout=2)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _handle_tts_state(self, payload: dict) -> None:
        if self._disposed:
            return
        if self._thread is None and self._root is None and self._active_window is None:
            return
        self._ensure_ui_thread()
        phase = str(payload.get("phase") or "")
        is_speaking = bool(payload.get("is_speaking"))
        self._jobs.put(lambda: self._apply_tts_state_on_ui(phase, is_speaking))

    def _apply_tts_state_on_ui(self, phase: str, is_speaking: bool) -> None:
        ui_state = self._speak_phase_to_ui_state(phase, is_speaking)
        if ui_state is not None:
            self._set_speak_button_state_on_ui(ui_state)

    def _ensure_ui_thread(self) -> None:
        if self._disposed:
            return
        if self._thread and self._thread.is_alive():
            return
        self._shutdown_requested = False
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
                    logger.exception("Popup UI job failed.")
            if self._shutdown_requested:
                return
            root.after(30, _pump)

        root.after(30, _pump)
        root.mainloop()
        self._root = None

    def _show_session_on_ui(self, session: PopupSession) -> None:
        if self._root is None:
            return
        self._destroy_active_window()
        session_state = session.snapshot()

        root = self._root
        window = ctk.CTkToplevel(root)
        self._active_window = window
        self._active_session = session
        window.title(f"ClipAI - {session_state.action_name}")
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
            text=f"ClipAI - {session_state.action_name}",
            font=("Microsoft JhengHei", 11, "bold"),
            text_color=POPUP_TITLE_COLOR,
            anchor="w",
        )
        title_label.pack(side="left", fill="y")
        self._title_label = title_label

        action_bar = ctk.CTkFrame(header_frame, fg_color="transparent")
        action_bar.pack(side="right")

        def _header_button(name: str, text: str, tooltip: str, command, *, width: int = 26) -> ctk.CTkButton:
            use_accent = name in {"speak", "copy", "archive"}
            button = ctk.CTkButton(
                action_bar,
                text=text,
                width=width,
                height=24,
                corner_radius=8,
                font=("Segoe UI Symbol", 10, "bold"),
                fg_color=BUTTON_ACCENT_BG if use_accent else "transparent",
                hover_color=BUTTON_ACCENT_HOVER if use_accent else ("#E8EEF5", "#232A35"),
                border_width=1,
                border_color=("#C9D7EA", "#32485E") if use_accent else ("#D8DEE8", "#2B3240"),
                text_color=("#294766", "#EEF4FB") if use_accent else ("gray10", "#DCE4EE"),
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
        _header_button("copy", ICON_COPY, "Copy Result", lambda: self._copy_current_output(session))
        _header_button("archive", ICON_ARCHIVE, "Archive Result", lambda: self._archive_current_output(session))
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
            placeholder_text=f"Follow-up ({session_state.round_count}/{session_state.max_rounds})",
            font=("Microsoft JhengHei", 9),
            height=26,
        )
        follow_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._follow_entry = follow_entry

        follow_hint = ctk.CTkLabel(
            follow_frame,
            text=f"{session_state.round_count}/{session_state.max_rounds}",
            font=("Microsoft JhengHei", 9),
            text_color=("gray45", "gray60"),
        )
        follow_hint.pack(side="right")
        self._follow_hint_label = follow_hint
        self._sync_follow_up_controls(session)

        meta_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        meta_row.pack(fill="x", padx=10, pady=(0, 5))
        meta_row.grid_columnconfigure(0, weight=1)
        meta_row.grid_columnconfigure(1, weight=0)
        self._meta_row = meta_row

        input_value = ctk.CTkLabel(
            meta_row,
            text=self._input_preview_for_session(session_state),
            font=("Microsoft JhengHei", 10),
            text_color=("gray52", "gray58"),
            justify="left",
            anchor="w",
        )
        input_value.grid(row=0, column=0, sticky="ew")
        self._input_label = input_value

        source_label = ctk.CTkLabel(
            meta_row,
            text=PopupMarkdownRenderer.source_label_for_session(session_state),
            font=("Microsoft JhengHei", 10),
            text_color=("gray50", "gray55"),
            anchor="e",
        )
        source_label.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self._source_label = source_label

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
            font=("Microsoft JhengHei", 11),
            wrap="word",
            padx=9,
            pady=7,
            borderwidth=0,
            highlightthickness=0,
            bg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]),
            fg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
            insertbackground=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
            selectbackground=SELECTION_BG_COLOR,
            selectforeground=SELECTION_FG_COLOR,
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
            self._destroy_active_window(window)

        def _close_if_focus_left() -> None:
            if not window.winfo_exists():
                return
            if self._is_pinned:
                return
            if time.monotonic() < self._close_suppressed_until:
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
        self._set_speak_button_state_on_ui(self._action_handler.is_speaking())

    def _destroy_active_window(self, window=None) -> None:
        target = window or self._active_window
        closing_active = target is not None and target == self._active_window
        session_id = self._active_session.session_id if closing_active and self._active_session is not None else None
        if target is not None:
            try:
                target.destroy()
            except Exception:
                logger.exception("Popup window destroy failed.")
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
        self._meta_row = None
        self._pin_button = None
        self._main_frame = None
        self._title_label = None
        self._source_label = None
        self._button_refs = {}
        self._pending_chunks = []
        self._chunk_flush_scheduled = False
        self._is_pinned = False
        self._close_suppressed_until = 0.0
        if session_id is not None and self._on_session_closed is not None:
            self._on_session_closed(session_id)

    def _suppress_auto_close(self, seconds: float = CLOSE_GRACE_SEC) -> None:
        self._close_suppressed_until = max(self._close_suppressed_until, time.monotonic() + seconds)

    def _bind_popup_shortcuts(self, window, session: PopupSession, close_cb) -> None:
        window.bind("<Escape>", close_cb)
        window.bind("<Control-c>", lambda event: self._copy_shortcut(event, session))
        window.bind("<Control-s>", lambda event: self._archive_shortcut(event, session))
        window.bind("<Control-slash>", self._toggle_follow_up_shortcut)
        window.bind("<Control-question>", self._toggle_follow_up_shortcut)
        window.bind("<Control-Alt-Q>", lambda event: self._speak_shortcut(event, session))
        window.bind("<Control-Alt-q>", lambda event: self._speak_shortcut(event, session))

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
        if (
            self._follow_frame is None
            or self._meta_row is None
            or self._active_window is None
            or not self._active_window.winfo_exists()
        ):
            return
        self._follow_visible = not self._follow_visible
        if self._follow_visible:
            self._clear_follow_up_entry_on_ui()
            self._follow_frame.pack(fill="x", padx=10, pady=(0, 4), before=self._meta_row)
            if self._follow_entry is not None:
                self._follow_entry.focus_set()
        else:
            self._follow_frame.pack_forget()
            if self._text_widget is not None:
                self._clear_text_selection_on_ui(self._text_widget)
                self._text_widget.focus_set()

    def _toggle_secondary_actions_on_ui(self) -> None:
        if self._secondary_row is None or self._meta_row is None:
            return
        self._secondary_visible = not self._secondary_visible
        if self._secondary_visible:
            self._secondary_row.pack(fill="x", padx=10, pady=(0, 4), before=self._meta_row)
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
        self._active_session.mark_input_ready(original_input)
        self._render_input_preview_on_ui(self._active_session)

    def _refresh_session_on_ui(self, session_id: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._pending_chunks = []
        self._chunk_flush_scheduled = False
        self._sync_session_header_on_ui(self._active_session)
        self._render_input_preview_on_ui(self._active_session)
        if self._text_widget is not None:
            self._render_session_text(self._text_widget, self._active_session)
        self._clear_follow_up_entry_on_ui()
        self._sync_follow_up_controls(self._active_session)

    def _set_follow_up_enabled_on_ui(self, session_id: str, enabled: bool) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._follow_entry is None:
            return
        session_state = self._active_session.snapshot()
        state = "normal" if enabled and session_state.can_continue() else "disabled"
        self._follow_entry.configure(state=state)
        if enabled:
            self._clear_follow_up_entry_on_ui()
            if self._text_widget is not None:
                self._text_widget.focus_set()

    def _append_chunk_on_ui(self, session_id: str, chunk: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._active_session.append_result_chunk(chunk)
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
        session_state = self._active_session.snapshot()
        del chunk
        streaming_text = self._result_text_for_session(session_state)
        text_widget.delete("1.0", "end")
        text_widget.insert("end", streaming_text, ("body",))
        if autoscroll:
            text_widget.see("end")
        text_widget.config(state="disabled")

    def _finalize_result_on_ui(self, session_id: str, content: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._active_session.mark_result_ready(content)
        self._pending_chunks = []
        self._chunk_flush_scheduled = False
        self._render_input_preview_on_ui(self._active_session)
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
        session_state = session.snapshot()
        if self._follow_hint_label is not None:
            self._follow_hint_label.configure(text=f"{session_state.round_count}/{session_state.max_rounds}")
        if self._follow_entry is not None:
            if session_state.can_continue():
                self._follow_entry.configure(
                    state="normal",
                    placeholder_text=f"Follow-up ({session_state.round_count}/{session_state.max_rounds})",
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
    def _clear_text_selection_on_ui(text_widget: tk.Text | None) -> None:
        if text_widget is None:
            return
        try:
            text_widget.tag_remove("sel", "1.0", "end")
            text_widget.mark_set("insert", "end-1c")
        except tk.TclError:
            return

    @staticmethod
    def _code_tag_palette(text_widget: tk.Text) -> tuple[str, str]:
        return PopupMarkdownRenderer.code_tag_palette(text_widget)

    @staticmethod
    def _render_session_text(text_widget: tk.Text, session: PopupSession) -> None:
        PopupMarkdownRenderer.render_session_text(text_widget, session)

    def _render_input_preview_on_ui(self, session: PopupSession) -> None:
        if self._input_label is not None:
            self._input_label.configure(text=self._input_preview_for_session(session))
        if self._source_label is not None:
            self._source_label.configure(text=PopupMarkdownRenderer.source_label_for_session(session))

    def _sync_session_header_on_ui(self, session: PopupSession) -> None:
        session_state = session.snapshot()
        title_text = f"ClipAI - {session_state.action_name}"
        if self._title_label is not None:
            self._title_label.configure(text=title_text)
        if self._active_window is not None:
            try:
                self._active_window.title(title_text)
            except tk.TclError:
                return

    @staticmethod
    def _insert_markdown(text_widget: tk.Text, content: str, base_tag: str = "body") -> None:
        PopupMarkdownRenderer.insert_markdown(text_widget, content, style=base_tag)

    @staticmethod
    def _insert_inline_markdown(text_widget: tk.Text, line: str, base_tags: tuple[str, ...]) -> None:
        del base_tags
        PopupMarkdownRenderer.insert_inline_markdown(text_widget, line, style="body")

    @staticmethod
    def _selected_output_or_full(text_widget: tk.Text | None, session: PopupSession) -> str:
        return PopupActionHandler.selected_output_or_full(text_widget, session)

    def _copy_current_output(self, session: PopupSession) -> None:
        try:
            self._suppress_auto_close()
            self._action_handler.copy_output(self._text_widget, session)
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
            self._action_handler.archive_output(self._text_widget, session)
            button = self._button_refs.get("archive")
            if button is not None:
                self._pulse_button(button, ICON_CHECK, SUCCESS_COLOR)
        except Exception:
            button = self._button_refs.get("archive")
            if button is not None:
                self._pulse_button(button, ICON_ERROR, ERROR_COLOR)

    def _toggle_speak(self, session: PopupSession) -> None:
        self._suppress_auto_close()
        speaking_state = self._action_handler.toggle_speak(self._text_widget, session)
        if speaking_state is None:
            return
        self._set_speak_button_state_on_ui(speaking_state)

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
            fg_color=BUTTON_ACCENT_BG,
            hover_color=BUTTON_ACCENT_HOVER,
            border_width=1,
            border_color=("#C9D7EA", "#32485E"),
            text_color=("#294766", "#EEF4FB"),
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
