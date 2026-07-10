from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import queue
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.commands import CloseSession, CopyResult, FollowUp, TogglePin, ToggleSpeech
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface


@dataclass
class _SessionView:
    dialog: BaseDialog
    surface: BaseResultSurface
    revision: int = -1


class ResultDialogPresenter:
    """One persistent Tk root that renders any number of session Toplevels."""

    def __init__(self) -> None:
        self._root = ctk.CTk()
        self._root.withdraw()
        self._updates: queue.Queue[SessionSnapshot] = queue.Queue()
        self._views: dict[str, _SessionView] = {}
        self._command_sink: Callable[[object], None] = lambda _command: None
        self._stopping = False

    def set_command_sink(self, sink: Callable[[object], None]) -> None:
        self._command_sink = sink

    def render(self, snapshot: SessionSnapshot) -> None:
        self._updates.put(snapshot)

    def run(self, command_pump: Callable[[], None]) -> None:
        def tick() -> None:
            if self._stopping:
                return
            command_pump()
            self._drain_updates()
            self._root.after(25, tick)

        self._root.after(0, tick)
        self._root.mainloop()

    def stop(self) -> None:
        def close_all() -> None:
            self._stopping = True
            for view in list(self._views.values()):
                view.dialog.close()
            self._views.clear()
            try:
                self._root.quit()
                self._root.destroy()
            except tk.TclError:
                pass

        self._root.after(0, close_all)

    def _drain_updates(self) -> None:
        while True:
            try:
                snapshot = self._updates.get_nowait()
            except queue.Empty:
                return
            self._apply(snapshot)

    def _apply(self, snapshot: SessionSnapshot) -> None:
        view = self._views.get(snapshot.session_id)
        if view is not None and snapshot.revision <= view.revision:
            return
        if snapshot.status in {SessionStatus.CLOSED, SessionStatus.CANCELLED}:
            if view is not None:
                view.dialog.close()
                self._views.pop(snapshot.session_id, None)
            return
        if view is None:
            view = self._create_view(snapshot.session_id)
            self._views[snapshot.session_id] = view
        view.revision = snapshot.revision
        view.dialog.set_pinned(snapshot.pinned)
        view.surface.set_title(snapshot.title)
        view.surface.set_source_preview(snapshot.source_preview)
        view.surface.set_model(snapshot.model)
        view.surface.close_button.configure(
            command=lambda sid=snapshot.session_id: self._command_sink(CloseSession(sid))
        )
        view.surface.pin_button.configure(
            command=lambda sid=snapshot.session_id: self._command_sink(TogglePin(sid))
        )
        if snapshot.status == SessionStatus.FAILED:
            view.dialog.flash("error")
            view.surface.set_content_chunks([(snapshot.error, "body")])
        elif snapshot.status == SessionStatus.COMPLETED:
            view.dialog.flash("success")
            view.surface.set_content_chunks([(snapshot.content, "body")])
        else:
            view.surface.set_loading(snapshot.status_text)
        view.surface.configure_standard_actions(
            on_speak=(lambda sid=snapshot.session_id: self._command_sink(ToggleSpeech(sid))) if "speaker" in snapshot.available_actions else None,
            on_copy=(lambda sid=snapshot.session_id: self._command_sink(CopyResult(sid))) if "copy" in snapshot.available_actions else None,
            on_follow_up=(lambda sid=snapshot.session_id: self._toggle_follow_up(sid)) if "follow_up" in snapshot.available_actions else None,
        )
        view.surface.set_speaker_active(snapshot.speaking)

    def _toggle_follow_up(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        if view.surface.follow_up_visible:
            view.surface.hide_follow_up()
            view.surface.set_follow_up_active(False)
            return
        view.surface.show_follow_up()
        view.surface.set_follow_up_active(True)

        def send() -> None:
            question = view.surface.follow_entry.get().strip()
            if question:
                view.surface.hide_follow_up()
                view.surface.set_follow_up_active(False)
                self._command_sink(FollowUp(session_id, question))

        view.surface.follow_send_button.configure(command=send)
        view.surface.follow_entry.bind("<Return>", lambda _event: send(), add="+")

    def _create_view(self, session_id: str) -> _SessionView:
        dialog = BaseDialog(
            title="ClipAI",
            width=460,
            height=300,
            position="cursor",
            background_color="#111111",
            surface_color="#2B2B2B",
            frameless=True,
            transparent_background=True,
            surface_inset=8,
            master=self._root,
        )
        surface = BaseResultSurface(dialog)
        surface.configure_standard_actions()
        dialog.root.bind("<FocusOut>", lambda _event, sid=session_id: self._close_if_outside(sid), add="+")
        return _SessionView(dialog=dialog, surface=surface)

    def _close_if_outside(self, session_id: str) -> None:
        def check() -> None:
            view = self._views.get(session_id)
            if view is None or view.dialog.pinned:
                return
            try:
                focused = view.dialog.root.focus_get()
                if focused is None or focused.winfo_toplevel() is not view.dialog.root:
                    self._command_sink(CloseSession(session_id))
            except tk.TclError:
                self._command_sink(CloseSession(session_id))

        self._root.after(100, check)
