from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import queue
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.commands import ActivateWorkflow, ArchiveResult, CloseSession, CopyResult, FollowUp, NavigateWorkflowBack, PasteResult, TogglePin, ToggleSpeech
from ClipAI.core.models import ActiveWorkflowContext
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface


@dataclass
class _SessionView:
    dialog: BaseDialog
    surface: BaseResultSurface
    revision: int = -1
    speaking: bool = False
    content: str = ""
    step_id: str | None = None


class ResultDialogPresenter:
    """One persistent Tk root that renders any number of session Toplevels."""

    def __init__(self) -> None:
        self._root = ctk.CTk()
        self._root.withdraw()
        self._updates: queue.Queue[SessionSnapshot] = queue.Queue()
        self._views: dict[str, _SessionView] = {}
        self._command_sink: Callable[[object], None] = lambda _command: None
        self._stopping = False
        self._destroyed = False
        self._tick_job: str | None = None
        self._active_workflow_id: str | None = None

    def set_command_sink(self, sink: Callable[[object], None]) -> None:
        self._command_sink = sink

    def active_workflow_context(self) -> ActiveWorkflowContext | None:
        workflow_id = self._active_workflow_id
        if workflow_id is None:
            return None
        view = self._views.get(workflow_id)
        if view is None or view.step_id is None or not view.content.strip():
            return None
        return ActiveWorkflowContext(
            workflow_id,
            view.step_id,
            view.content,
            view.surface.selected_text(),
        )

    def render(self, snapshot: SessionSnapshot) -> None:
        self._updates.put(snapshot)

    def run(self, command_pump: Callable[[], None]) -> None:
        def tick() -> None:
            self._tick_job = None
            if self._stopping:
                return
            command_pump()
            self._drain_updates()
            self._tick_job = self._root.after(25, tick)

        self._tick_job = self._root.after(0, tick)
        try:
            self._root.mainloop()
        finally:
            self._destroy_root()

    def stop(self) -> None:
        if self._stopping or self._destroyed:
            return
        self._quit_mainloop()

    def _quit_mainloop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        if self._tick_job is not None:
            try:
                self._root.after_cancel(self._tick_job)
            except tk.TclError:
                pass
            self._tick_job = None
        for view in list(self._views.values()):
            view.dialog.close()
        self._views.clear()
        try:
            self._root.quit()
        except tk.TclError:
            pass

    def _destroy_root(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        try:
            self._root.destroy()
        except tk.TclError:
            pass

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
                if self._active_workflow_id == snapshot.session_id:
                    self._active_workflow_id = None
            return
        created = view is None
        if view is None:
            view = self._create_view(snapshot.session_id)
            self._views[snapshot.session_id] = view
        view.revision = snapshot.revision
        if created or self._active_workflow_id is None:
            self._active_workflow_id = snapshot.session_id
        view.content = snapshot.content
        if snapshot.displayed_step_index >= 0:
            view.step_id = snapshot.steps[snapshot.displayed_step_index].step_id
        view.surface.set_pinned_state(snapshot.pinned)
        view.surface.set_title(snapshot.title)
        view.surface.set_source_preview(snapshot.source_preview)
        view.surface.set_model(snapshot.model)
        view.surface.close_button.configure(
            command=lambda sid=snapshot.session_id: self._command_sink(CloseSession(sid))
        )
        view.surface.pin_button.configure(
            command=lambda sid=snapshot.session_id: self._toggle_pin(sid)
        )
        view.surface.configure_back_action(
            (lambda sid=snapshot.session_id: self._command_sink(NavigateWorkflowBack(sid)))
            if snapshot.can_navigate_back
            else None
        )
        if snapshot.status == SessionStatus.FAILED:
            view.dialog.flash("error")
            if snapshot.content:
                view.surface.set_content_chunks([(snapshot.content, "body")])
                view.surface.set_source_preview(f"Failed: {snapshot.error}")
            else:
                view.surface.set_content_chunks([(snapshot.error, "body")])
        elif snapshot.status == SessionStatus.COMPLETED:
            view.dialog.flash("success")
            view.surface.set_content_chunks([(snapshot.content, "body")])
        else:
            if snapshot.content:
                view.surface.set_content_chunks([(snapshot.content, "body")])
                view.surface.set_source_preview(snapshot.status_text)
            else:
                view.surface.set_loading(snapshot.status_text)
        view.surface.configure_standard_actions(
            on_speak=(lambda sid=snapshot.session_id: self._toggle_speech(sid)) if "speaker" in snapshot.available_actions else None,
            on_copy=(lambda sid=snapshot.session_id: self._copy(sid)) if "copy" in snapshot.available_actions else None,
            on_paste=(lambda sid=snapshot.session_id: self._paste(sid)) if "paste" in snapshot.available_actions else None,
            on_archive=(lambda sid=snapshot.session_id: self._archive(sid)) if "archive" in snapshot.available_actions else None,
            on_follow_up=(lambda sid=snapshot.session_id: self._toggle_follow_up(sid)) if "follow_up" in snapshot.available_actions else None,
        )
        view.speaking = snapshot.speaking
        view.surface.set_speaker_active(snapshot.speaking)

    def _send_text_command(self, session_id: str, command_type) -> None:
        view = self._views.get(session_id)
        text = view.surface.selected_text() if view is not None else None
        self._command_sink(command_type(session_id, text))

    def _copy(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        view.surface.pulse_standard_action("copy")
        self._send_text_command(session_id, CopyResult)

    def _toggle_speech(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        self._send_text_command(session_id, ToggleSpeech)

    def _archive(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        view.surface.pulse_standard_action("archive")
        self._command_sink(ArchiveResult(session_id))

    def _paste(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        text = view.surface.selected_text()
        view.surface.set_standard_action_enabled("paste", False)
        view.dialog.root.withdraw()
        self._command_sink(PasteResult(session_id, text))

    def _toggle_pin(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        view.surface.toggle_pin()
        self._command_sink(TogglePin(session_id))

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
        dialog.root.bind("<FocusIn>", lambda _event, sid=session_id: self._activate(sid), add="+")
        dialog.root.bind("<ButtonPress>", lambda _event, sid=session_id: self._activate(sid), add="+")
        return _SessionView(dialog=dialog, surface=surface)

    def _activate(self, session_id: str) -> None:
        self._active_workflow_id = session_id
        self._command_sink(ActivateWorkflow(session_id))

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
