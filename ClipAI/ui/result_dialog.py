from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import queue
import tkinter as tk
import uuid

import customtkinter as ctk

from ClipAI.core.commands import ActivateWorkflow, ArchiveResult, CloseSession, CopyResult, FollowUp, NavigateWorkflowBack, PasteResult, SubmitActionFeedback, TogglePin, ToggleSpeech
from ClipAI.core.models import ActiveWorkflowContext, FeedbackOutcome, OutputOperationResult, ProviderSettingsState
from ClipAI.core.ports import DisplayMetricsReader
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface
from ClipAI.ui.popup_layout import PopupLayoutPolicy
from ClipAI.ui.provider_settings import ProviderSettingsDialog


@dataclass
class _SessionView:
    dialog: BaseDialog
    surface: BaseResultSurface
    revision: int = -1
    speaking: bool = False
    content: str = ""
    step_id: str | None = None
    focus_lifecycle: PopupFocusLifecycle | None = None
    flashed_completion_keys: set[str] = field(default_factory=set)
    output_operations: dict[str, str] = field(default_factory=dict)
    rendered_content_key: tuple[object, ...] | None = None
    shown_guidance_keys: set[str] = field(default_factory=set)


@dataclass
class PopupFocusLifecycle:
    """Gate toolkit focus events until a popup is registered and shown."""

    registered: bool = False
    shown: bool = False
    initial_focus_established: bool = False
    outside_check_pending: bool = False

    @property
    def ready(self) -> bool:
        return self.registered and self.shown and self.initial_focus_established

    def request_outside_check(self) -> bool:
        if not self.ready or self.outside_check_pending:
            return False
        self.outside_check_pending = True
        return True

    def finish_outside_check(self, *, pinned: bool, focused_inside: bool) -> bool:
        self.outside_check_pending = False
        return self.ready and not pinned and not focused_inside


class ResultDialogPresenter:
    """One persistent Tk root that renders any number of session Toplevels."""

    def __init__(self, display_metrics: DisplayMetricsReader | None = None, layout_policy: PopupLayoutPolicy | None = None) -> None:
        self._root = ctk.CTk()
        self._root.withdraw()
        self._updates: queue.Queue[SessionSnapshot] = queue.Queue()
        self._output_updates: queue.Queue[OutputOperationResult] = queue.Queue()
        self._views: dict[str, _SessionView] = {}
        self._command_sink: Callable[[object], None] = lambda _command: None
        self._stopping = False
        self._destroyed = False
        self._tick_job: str | None = None
        self._active_workflow_id: str | None = None
        self._display_metrics = display_metrics
        self._layout_policy = layout_policy or PopupLayoutPolicy()
        self._provider_settings_dialog: ProviderSettingsDialog | None = None

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

    def present_output_operation(self, result: OutputOperationResult) -> None:
        self._output_updates.put(result)

    def show_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is None:
            self._provider_settings_dialog = ProviderSettingsDialog(self._root, self._command_sink)
        self._provider_settings_dialog.apply(state)

    def set_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.apply(state)

    def _apply_output_operation(self, result: OutputOperationResult) -> None:
        view = self._views.get(result.workflow_id)
        if view is None:
            return
        if not view.dialog.is_alive():
            self._evict_view(result.workflow_id, view)
            return
        slot_id = "speaker" if result.kind == "speech" else result.kind
        if result.state == "pending":
            view.output_operations[result.kind] = result.operation_id
            if result.kind in {"copy", "paste", "archive"}:
                view.surface.set_standard_action_enabled(slot_id, False)
            return
        if view.output_operations.get(result.kind) != result.operation_id:
            return
        view.output_operations.pop(result.kind, None)
        if result.kind in {"copy", "paste", "archive"}:
            view.surface.set_standard_action_enabled(slot_id, True)
        if result.state == "succeeded":
            view.surface.pulse_standard_action(slot_id)
            if result.kind == "archive" and not view.surface.overflow_expanded:
                view.surface.show_action_message("已封存", 1000)
        elif result.state == "failed":
            view.surface.pulse_standard_action_error(slot_id)
            if result.error is not None:
                view.surface.show_action_message(result.error.message, 1500)

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
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.destroy()
            self._provider_settings_dialog = None
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
                self._apply_output_operation(self._output_updates.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                snapshot = self._updates.get_nowait()
            except queue.Empty:
                return
            self._apply(snapshot)

    def _apply(self, snapshot: SessionSnapshot) -> None:
        view = self._views.get(snapshot.session_id)
        if view is not None and not view.dialog.is_alive():
            self._evict_view(snapshot.session_id, view)
            return
        if view is not None and snapshot.revision <= view.revision:
            return
        if snapshot.status in {SessionStatus.CLOSED, SessionStatus.CANCELLED}:
            if view is not None:
                view.dialog.close()
                self._evict_view(snapshot.session_id, view)
            return
        created = view is None
        if view is None:
            view = self._create_view(snapshot.session_id)
            self._views[snapshot.session_id] = view
            self._register_view(snapshot.session_id, view)
        view.revision = snapshot.revision
        if created or self._active_workflow_id is None:
            self._active_workflow_id = snapshot.session_id
        previous_step_id = view.step_id
        view.content = snapshot.content
        if snapshot.displayed_step_index >= 0:
            view.step_id = snapshot.steps[snapshot.displayed_step_index].step_id
        if previous_step_id is not None and view.step_id != previous_step_id:
            view.surface.close_feedback_overlay()
        view.surface.set_pinned_state(snapshot.pinned)
        view.surface.set_title(snapshot.title)
        view.surface.set_source_preview(snapshot.source_preview)
        view.surface.set_model(snapshot.model)
        view.surface.configure_action_contract(snapshot.action_feedback_contract, snapshot.input_source)
        guidance_key = view.step_id or ""
        if snapshot.status == SessionStatus.COMPLETED and snapshot.show_guidance_hint and guidance_key not in view.shown_guidance_keys:
            view.shown_guidance_keys.add(guidance_key)
            view.surface.show_action_guidance_hint()
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
        content_key = _content_render_key(snapshot)
        content_changed = content_key != view.rendered_content_key
        if snapshot.status == SessionStatus.FAILED:
            view.dialog.flash("error")
            if content_changed:
                if snapshot.content:
                    view.surface.set_content_chunks([(snapshot.content, "body")])
                    view.surface.set_source_preview(f"Failed: {snapshot.error}")
                else:
                    view.surface.set_content_chunks([(snapshot.error, "body")])
        elif snapshot.status == SessionStatus.COMPLETED:
            completion_key = view.step_id or snapshot.content
            if completion_key and completion_key not in view.flashed_completion_keys:
                view.flashed_completion_keys.add(completion_key)
                view.dialog.flash("success")
            if content_changed:
                if snapshot.presentation is not None:
                    view.surface.set_presentation_document(snapshot.presentation)
                else:
                    view.surface.set_content_chunks([(snapshot.content, "body")])
        else:
            if content_changed:
                if snapshot.content:
                    view.surface.set_content_chunks([(snapshot.content, "body")])
                    view.surface.set_source_preview(snapshot.status_text)
                else:
                    view.surface.set_loading(snapshot.status_text)
        if content_changed:
            view.rendered_content_key = content_key
        view.surface.configure_standard_actions(
            on_speak=(lambda sid=snapshot.session_id: self._toggle_speech(sid)) if "speaker" in snapshot.available_actions else None,
            on_copy=(lambda sid=snapshot.session_id: self._copy(sid)) if "copy" in snapshot.available_actions else None,
            on_paste=(lambda sid=snapshot.session_id: self._paste(sid)) if "paste" in snapshot.available_actions else None,
            on_archive=(lambda sid=snapshot.session_id: self._archive(sid)) if "archive" in snapshot.available_actions else None,
            on_follow_up=(lambda sid=snapshot.session_id: self._toggle_follow_up(sid)) if "follow_up" in snapshot.available_actions else None,
        )
        view.speaking = snapshot.speaking
        view.surface.set_speaker_active(snapshot.speaking)
        if snapshot.status == SessionStatus.COMPLETED and snapshot.action_feedback_contract is not None and view.step_id is not None:
            view.surface.configure_feedback(
                snapshot.action_feedback_contract,
                snapshot.feedback_state,
                snapshot.feedback_message,
                lambda outcome, reason, note, save_case, sid=snapshot.session_id, step=view.step_id: self._submit_feedback(
                    sid, step, outcome, reason, note, save_case
                ),
            )
        else:
            view.surface.hide_feedback()

    def _evict_view(self, session_id: str, view: _SessionView) -> None:
        if self._views.get(session_id) is view:
            self._views.pop(session_id, None)
        if self._active_workflow_id == session_id:
            self._active_workflow_id = None

    def _send_text_command(self, session_id: str, command_type) -> None:
        view = self._views.get(session_id)
        text = view.surface.selected_text() if view is not None else None
        self._command_sink(command_type(session_id, text))

    def _copy(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        operation_id = uuid.uuid4().hex
        view.output_operations["copy"] = operation_id
        text = view.surface.selected_text()
        self._command_sink(CopyResult(session_id, text, operation_id))

    def _toggle_speech(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        text = view.surface.selected_text()
        self._command_sink(ToggleSpeech(session_id, text, uuid.uuid4().hex))

    def _archive(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        operation_id = uuid.uuid4().hex
        view.output_operations["archive"] = operation_id
        self._command_sink(ArchiveResult(session_id, view.surface.selected_text(), operation_id))

    def _paste(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        self._command_sink(PasteResult(session_id, view.surface.selected_text(), uuid.uuid4().hex))

    def _toggle_pin(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        view.surface.toggle_pin()
        self._command_sink(TogglePin(session_id))

    def _submit_feedback(
        self,
        session_id: str,
        step_id: str,
        outcome: FeedbackOutcome,
        reason: str,
        note: str,
        save_case: bool,
    ) -> None:
        self._command_sink(SubmitActionFeedback(
            session_id=session_id,
            step_id=step_id,
            operation_id=uuid.uuid4().hex,
            outcome=outcome,
            reason=reason,
            note=note,
            save_case=save_case,
        ))

    def _toggle_feedback(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        if not view.surface.toggle_feedback_overlay():
            view.surface.show_action_message("此 Recipe 尚未啟用回饋")

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
        metrics = self._display_metrics.current() if self._display_metrics is not None else None
        bounds = self._layout_policy.calculate(metrics) if metrics is not None else None
        dialog = BaseDialog(
            title="ClipAI",
            width=bounds.width if bounds else 400,
            height=bounds.height if bounds else 320,
            position="cursor",
            background_color="#111111",
            surface_color="#2B2B2B",
            frameless=True,
            transparent_background=True,
            surface_inset=8,
            master=self._root,
            x=bounds.x if bounds else None,
            y=bounds.y if bounds else None,
            minimum_width=340,
            minimum_height=220,
            hide_from_task_switcher=True,
        )
        surface = BaseResultSurface(dialog)
        surface.configure_standard_actions()
        return _SessionView(dialog=dialog, surface=surface, focus_lifecycle=PopupFocusLifecycle())

    def _register_view(self, session_id: str, view: _SessionView) -> None:
        lifecycle = view.focus_lifecycle or PopupFocusLifecycle()
        view.focus_lifecycle = lifecycle
        lifecycle.registered = True
        dialog = view.dialog
        dialog.root.bind("<FocusOut>", lambda _event, sid=session_id: self._close_if_outside(sid), add="+")
        dialog.root.bind("<FocusIn>", lambda _event, sid=session_id: self._activate(sid), add="+")
        dialog.root.bind("<ButtonPress>", lambda _event, sid=session_id: self._activate(sid), add="+")
        dialog.root.bind("<Control-q>", lambda _event, sid=session_id: self._shortcut(self._toggle_speech, sid), add="+")
        dialog.root.bind("<Control-c>", lambda _event, sid=session_id: self._shortcut(self._copy, sid), add="+")
        dialog.root.bind("<Control-s>", lambda _event, sid=session_id: self._shortcut(self._archive, sid), add="+")
        dialog.root.bind("<Control-r>", lambda _event, sid=session_id: self._shortcut(self._toggle_feedback, sid), add="+")
        lifecycle.shown = True

        def establish_initial_focus() -> None:
            if session_id not in self._views:
                return
            dialog.lifecycle.focus()
            lifecycle.initial_focus_established = True

        dialog.lifecycle.schedule(0, establish_initial_focus)

    def _shortcut(self, action: Callable[[str], None], session_id: str) -> str:
        if self._active_workflow_id == session_id:
            action(session_id)
        return "break"

    def _activate(self, session_id: str) -> None:
        self._active_workflow_id = session_id
        self._command_sink(ActivateWorkflow(session_id))

    def _close_if_outside(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        lifecycle = view.focus_lifecycle
        if lifecycle is None or not lifecycle.request_outside_check():
            return

        def check() -> None:
            view = self._views.get(session_id)
            if view is None:
                return
            try:
                focused = view.dialog.root.focus_get()
                focused_inside = focused is not None and focused.winfo_toplevel() is view.dialog.root
                if lifecycle.finish_outside_check(pinned=view.dialog.pinned, focused_inside=focused_inside):
                    view.surface.collapse_overflow()
                    self._command_sink(CloseSession(session_id))
            except tk.TclError:
                if lifecycle.finish_outside_check(pinned=view.dialog.pinned, focused_inside=False):
                    view.surface.collapse_overflow()
                    self._command_sink(CloseSession(session_id))

        self._root.after(100, check)


def _content_render_key(snapshot: SessionSnapshot) -> tuple[object, ...]:
    """Only content-affecting state may replace the textbox and reset its scroll."""
    if snapshot.status == SessionStatus.FAILED:
        return (snapshot.status, snapshot.content, snapshot.error)
    if snapshot.status == SessionStatus.COMPLETED:
        return (snapshot.status, snapshot.content, snapshot.presentation)
    return (snapshot.status, snapshot.content, snapshot.status_text, snapshot.presentation)
