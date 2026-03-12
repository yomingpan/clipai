from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from clipai.platform.clipboard import write_clipboard_text
from clipai.services.archive_service import ArchiveService
from clipai.ui.result_popup.popup_session import PopupSession
from clipai.ui.tooltip import attach_tooltip

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

BRAND_COLOR = "#3B8ED0"
SUCCESS_COLOR = "#2E9E5B"
ERROR_COLOR = "#D64545"


class PopupPresenter:
    def __init__(self, on_follow_up: Callable[[PopupSession, str], None] | None = None) -> None:
        self._archive_service = ArchiveService()
        self._on_follow_up = on_follow_up
        self._jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root: ctk.CTk | None = None
        self._active_window = None
        self._active_session: PopupSession | None = None
        self._text_widget = None
        self._follow_entry = None
        self._input_label = None
        self._follow_hint_label = None
        self._main_frame = None
        self._title_label = None
        self._ready = threading.Event()

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
        if self._active_window is not None:
            try:
                self._active_window.destroy()
            except Exception:
                pass
            self._active_window = None
            self._active_session = None
            self._text_widget = None
            self._follow_entry = None
            self._input_label = None
            self._follow_hint_label = None
            self._main_frame = None
            self._title_label = None

        root = self._root
        window = ctk.CTkToplevel(root)
        self._active_window = window
        self._active_session = session
        window.title(f"ClipAI - {session.action_name}")
        window.configure(fg_color=("#F7F8FA", "#111318"))
        window.overrideredirect(True)

        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = max(500, min(760, int(screen_w * 0.32)))
        height = max(380, min(620, int(screen_h * 0.42)))
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
            corner_radius=14,
            border_width=1,
            border_color=BRAND_COLOR,
        )
        main_frame.pack(fill="both", expand=True)
        self._main_frame = main_frame

        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=36)
        header_frame.pack(fill="x", padx=14, pady=(14, 6))
        header_frame.pack_propagate(False)

        title_label = ctk.CTkLabel(
            header_frame,
            text=f"ClipAI - {session.action_name}",
            font=("Microsoft JhengHei", 12, "bold"),
            text_color=BRAND_COLOR,
            anchor="w",
        )
        title_label.pack(side="left", fill="y")
        self._title_label = title_label

        action_bar = ctk.CTkFrame(header_frame, fg_color="transparent")
        action_bar.pack(side="right")

        def _icon_button(icon: str, tooltip: str, command, accent: bool = False):
            button = ctk.CTkButton(
                action_bar,
                text=icon,
                width=32,
                height=28,
                corner_radius=8,
                font=("Segoe UI Symbol", 12, "bold"),
                fg_color=(BRAND_COLOR if accent else "transparent"),
                hover_color=("#2B6E9E" if accent else ("#E8EEF5", "#232A35")),
                border_width=(0 if accent else 1),
                border_color=("#D8DEE8", "#2B3240"),
                text_color=("white" if accent else ("gray10", "#DCE4EE")),
                command=command,
            )
            button.pack(side="left", padx=(6, 0))
            attach_tooltip(button, tooltip)
            return button

        _icon_button("◉", "播放聲音", lambda: None)
        _icon_button("⎘", "複製", lambda: self._copy_from_widget(text_widget, session))
        _icon_button("◎", "Archive", lambda: self._archive_service.append_session(session))
        _icon_button("✦", "Deep Think", lambda: None, accent=True)

        follow_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        follow_frame.pack(fill="x", padx=14, pady=(0, 8))

        follow_entry = ctk.CTkEntry(
            follow_frame,
            placeholder_text=f"Follow-up ({session.round_count}/{session.max_rounds})",
            font=("Microsoft JhengHei", 10),
            height=30,
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

        text_container = ctk.CTkFrame(
            main_frame,
            corner_radius=10,
            border_width=1,
            border_color=("#D8DEE8", "#2B3240"),
            fg_color=("#FCFCFD", "#141922"),
        )
        text_container.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        text_widget = tk.Text(
            text_container,
            font=("Microsoft JhengHei", 11),
            wrap="word",
            padx=14,
            pady=14,
            borderwidth=0,
            highlightthickness=0,
            bg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]),
            fg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
            insertbackground=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
        )
        text_widget.pack(fill="both", expand=True, padx=2, pady=2)
        self._text_widget = text_widget
        self._render_session_text(text_widget, session)

        input_frame = ctk.CTkFrame(
            main_frame,
            corner_radius=8,
            fg_color=("#F2F5F9", "#141922"),
        )
        input_frame.pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkLabel(
            input_frame,
            text="Input",
            font=("Microsoft JhengHei", 10, "bold"),
            text_color=("gray35", "gray65"),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))

        input_value = ctk.CTkLabel(
            input_frame,
            text=session.original_input,
            font=("Microsoft JhengHei", 10),
            text_color=("gray45", "gray60"),
            justify="left",
            anchor="w",
            wraplength=width - 60,
        )
        input_value.pack(fill="x", padx=10, pady=(0, 8))
        self._input_label = input_value

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
            self._set_follow_up_enabled_on_ui(session.session_id, False)
            self._on_follow_up(session, prompt_text)
            return "break"

        follow_entry.bind("<Return>", _submit_follow_up)

        def _close(event=None) -> None:
            del event
            try:
                if window.winfo_exists():
                    window.destroy()
            finally:
                if self._active_window is window:
                    self._active_window = None
                    self._active_session = None
                    self._text_widget = None
                    self._follow_entry = None
                    self._input_label = None
                    self._follow_hint_label = None
                    self._main_frame = None
                    self._title_label = None

        def _close_if_focus_left() -> None:
            if not window.winfo_exists():
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
            if not window.winfo_exists():
                return
            window.after(120, _close_if_focus_left)

        window.protocol("WM_DELETE_WINDOW", _close)
        window.bind("<Escape>", _close)
        window.bind("<FocusOut>", _schedule_focus_check)
        window.after(60, lambda: window.focus_force())
        window.after(100, lambda: text_widget.focus_set())
        window.lift()
        window.attributes("-topmost", True)
        window.after(300, lambda: window.winfo_exists() and window.attributes("-topmost", False))

    def _update_input_on_ui(self, session_id: str, original_input: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._active_session.original_input = original_input
        if self._input_label is not None:
            self._input_label.configure(text=original_input)

    def _refresh_session_on_ui(self, session_id: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._text_widget is not None:
            self._render_session_text(self._text_widget, self._active_session)
        self._sync_follow_up_controls(self._active_session)

    def _set_follow_up_enabled_on_ui(self, session_id: str, enabled: bool) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._follow_entry is None:
            return
        state = "normal" if enabled and self._active_session.can_continue() else "disabled"
        self._follow_entry.configure(state=state)

    def _append_chunk_on_ui(self, session_id: str, chunk: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        if self._active_session.latest_result.strip() == "Connecting...":
            self._active_session.latest_result = ""
        self._active_session.latest_result += chunk
        if self._text_widget is not None:
            self._render_session_text(self._text_widget, self._active_session)

    def _finalize_result_on_ui(self, session_id: str, content: str) -> None:
        if self._active_session is None or self._active_session.session_id != session_id:
            return
        self._active_session.latest_result = content
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
            duration_ms = 0

        self._apply_status_color(color)
        if duration_ms > 0:
            self._active_window.after(
                duration_ms,
                lambda: self._active_window
                and self._active_window.winfo_exists()
                and self._apply_status_color(BRAND_COLOR),
            )

    def _apply_status_color(self, color: str) -> None:
        if self._main_frame is not None:
            self._main_frame.configure(border_color=color)
        if self._title_label is not None:
            self._title_label.configure(text_color=color)

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

    @staticmethod
    def _render_session_text(text_widget: tk.Text, session: PopupSession) -> None:
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.tag_configure("latest")
        text_widget.tag_configure("history", foreground="#7A7F87")
        text_widget.insert("end", session.latest_result.strip(), ("latest",))
        if session.rounds:
            for item in session.rounds:
                text_widget.insert("end", f"\n\n--- round {item.round_index} ---\n", ("history",))
                label = "Deep Think" if item.kind == "deep_think" else "Follow-up"
                text_widget.insert("end", f"{label}: {item.prompt_text.strip()}\n", ("history",))
                text_widget.insert("end", item.result_text.strip(), ("history",))
        text_widget.config(state="disabled")

    @staticmethod
    def _copy_from_widget(text_widget: tk.Text, session: PopupSession) -> None:
        try:
            selection = text_widget.get("sel.first", "sel.last").strip()
        except tk.TclError:
            selection = ""
        write_clipboard_text(selection or session.render_full_text())
