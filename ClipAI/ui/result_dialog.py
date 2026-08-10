from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import queue
import threading
import tkinter as tk
import uuid

import customtkinter as ctk

from ClipAI.core.commands import ActivateWorkflow, ArchiveResult, CancelVoiceCapture, CloseSession, ControlSurfaceActivated, ControlSurfaceReleased, CopyResult, FollowUp, NavigateWorkflowBack, PasteResult, StopVoiceCapture, SubmitActionFeedback, TogglePin, ToggleSpeech, UpdateVoiceDraft, WorkflowAttentionCompleted
from ClipAI.core.models import ActiveWorkflowContext, ControlSurfaceRef, FeedbackOutcome, OutputOperationResult, PasteTarget, ProviderSettingsState, ShortcutGuideSnapshot, WorkflowAttention
from ClipAI.core.ports import DisplayMetricsReader
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface
from ClipAI.ui.pointer_input import PointerPressReader, WindowsPointerPressReader
from ClipAI.ui.popup_external_output import FocusEntered, FocusPopup, OutsideFocusCheckRequested, OutsideFocusObserved, OutsidePointerPressed, OwnedDialogClosed, OwnedDialogOpened, PopupExternalOutputTransitions, PopupRegistered, PopupShown, PopupTransitionAction, PulseOutputAction, ReportControlSurfaceReleased, RequestPopupClose, ScheduleOutsideFocusCheck, SetFocusProjection, SetOutputActionEnabled, SetPopupVisibility, ShowOutputMessage
from ClipAI.ui.popup_layout import PopupLayoutPolicy
from ClipAI.ui.provider_settings import ProviderSettingsDialog
from ClipAI.ui.shortcut_guide import ShortcutGuideDialog
from ClipAI.ui.voice_setup import VoiceSetupDialog


# Windows Tk maps Num Lock to Mod1 (0x0008), while physical Alt uses
# the separate 0x00020000 state bit. Lock states must not disable Ctrl shortcuts.
_POPUP_SHORTCUT_ALLOWED_MODIFIERS = 0x0002 | 0x0004 | 0x0008 | 0x0010


@dataclass
class _SessionView:
    dialog: BaseDialog
    surface: BaseResultSurface
    revision: int = -1
    speaking: bool = False
    content: str = ""
    step_id: str | None = None
    external_output: PopupExternalOutputTransitions = field(default_factory=PopupExternalOutputTransitions)
    flashed_completion_keys: set[str] = field(default_factory=set)
    rendered_content_key: tuple[object, ...] | None = None
    shown_guidance_keys: set[str] = field(default_factory=set)
    close_requested: bool = False
    last_snapshot: SessionSnapshot | None = None
    voice_draft_revision: int = 0
    voice_draft_editing: bool = True
    voice_stop_button: object | None = None
    voice_cancel_button: object | None = None


@dataclass(frozen=True)
class WorkflowRenderPatch:
    header: bool
    content: bool
    actions: bool
    feedback: bool
    visual_state: bool


class LatestSnapshotMailbox:
    """Keep only the highest pending revision for each Workflow."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, SessionSnapshot] = {}

    def put(self, snapshot: SessionSnapshot) -> None:
        with self._lock:
            current = self._latest.get(snapshot.session_id)
            if current is None or snapshot.revision > current.revision:
                self._latest[snapshot.session_id] = snapshot

    def drain(self) -> tuple[SessionSnapshot, ...]:
        with self._lock:
            latest, self._latest = self._latest, {}
        return tuple(latest.values())


class ResultDialogPresenter:
    """One persistent Tk root that renders any number of session Toplevels."""

    def __init__(
        self,
        display_metrics: DisplayMetricsReader | None = None,
        layout_policy: PopupLayoutPolicy | None = None,
        pointer_press_reader: PointerPressReader | None = None,
    ) -> None:
        self._root = ctk.CTk()
        self._root.withdraw()
        self._updates = LatestSnapshotMailbox()
        self._output_updates: queue.Queue[OutputOperationResult] = queue.Queue()
        self._paste_target_updates: queue.Queue[PasteTarget | None] = queue.Queue()
        self._attention_updates: queue.Queue[WorkflowAttention] = queue.Queue()
        self._views: dict[str, _SessionView] = {}
        self._command_sink: Callable[[object], None] = lambda _command: None
        self._stopping = False
        self._destroyed = False
        self._tick_job: str | None = None
        self._paste_target: PasteTarget | None = None
        self._display_metrics = display_metrics
        self._layout_policy = layout_policy or PopupLayoutPolicy()
        self._pointer_press_reader = pointer_press_reader or WindowsPointerPressReader()
        self._provider_settings_dialog: ProviderSettingsDialog | None = None
        self._shortcut_guide_dialog: ShortcutGuideDialog | None = None
        self._shortcut_guide_focus_hold_active = False
        self._shortcut_guide_focus_return: tuple[str, _SessionView] | None = None
        self._voice_setup_dialog: VoiceSetupDialog | None = None

    def set_command_sink(self, sink: Callable[[object], None]) -> None:
        self._command_sink = sink

    def workflow_context(self, workflow_id: str) -> ActiveWorkflowContext | None:
        view = self._interactive_view(workflow_id)
        if view is None or not view.content.strip():
            return None
        if view.step_id is None:
            if view.last_snapshot is None or view.last_snapshot.status is not SessionStatus.VOICE_REVIEW:
                return None
            step_id = "voice-origin"
        else:
            step_id = view.step_id
        return ActiveWorkflowContext(
            workflow_id,
            step_id,
            view.content,
            view.surface.selected_text(),
        )

    def voice_draft_selection_range(self, workflow_id: str) -> tuple[int, int] | None:
        view = self._interactive_view(workflow_id)
        if view is None or view.last_snapshot is None or view.last_snapshot.status is not SessionStatus.VOICE_REVIEW:
            return None
        return view.surface.selection_range()

    def render(self, snapshot: SessionSnapshot) -> None:
        self._updates.put(snapshot)

    def present_output_operation(self, result: OutputOperationResult) -> None:
        self._output_updates.put(result)

    def present_paste_target(self, target: PasteTarget | None) -> None:
        self._paste_target_updates.put(target)

    def present_workflow_attention(self, attention: WorkflowAttention) -> None:
        self._attention_updates.put(attention)

    def show_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is None:
            self._provider_settings_dialog = ProviderSettingsDialog(self._root, self._command_sink)
        self._provider_settings_dialog.apply(state)

    def set_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.apply(state)

    def close_provider_settings(self) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.close()

    def show_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None:
        self._hold_focus_for_shortcut_guide()
        if self._shortcut_guide_dialog is None:
            self._shortcut_guide_dialog = ShortcutGuideDialog(self._root, self._command_sink)
        self._shortcut_guide_dialog.show(snapshot)

    def set_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None:
        if self._shortcut_guide_dialog is not None:
            self._shortcut_guide_dialog.apply(snapshot)

    def close_shortcut_guide(self) -> None:
        if self._shortcut_guide_dialog is not None:
            self._shortcut_guide_dialog.close()
        self._restore_focus_after_shortcut_guide()

    def show_voice_setup(self) -> None:
        if self._voice_setup_dialog is None:
            self._voice_setup_dialog = VoiceSetupDialog(self._root, self._command_sink)
        self._voice_setup_dialog.show()

    def close_voice_setup(self) -> None:
        if self._voice_setup_dialog is not None:
            self._voice_setup_dialog.close()

    def set_voice_projection(self, projection) -> None:
        if self._voice_setup_dialog is not None:
            self._voice_setup_dialog.set_voice_projection(projection)

    def _hold_focus_for_shortcut_guide(self) -> None:
        if self._shortcut_guide_focus_hold_active:
            return
        self._shortcut_guide_focus_hold_active = True
        self._shortcut_guide_focus_return = None
        for workflow_id, view in self._views.items():
            if (
                self._interactive_view(workflow_id) is not view
                or not view.external_output.owns_focus
            ):
                continue
            self._apply_transition_actions(
                workflow_id,
                view,
                view.external_output.focus(OwnedDialogOpened()),
            )
            self._shortcut_guide_focus_return = (workflow_id, view)
            return

    def _restore_focus_after_shortcut_guide(self) -> None:
        if not self._shortcut_guide_focus_hold_active:
            return
        self._shortcut_guide_focus_hold_active = False
        target, self._shortcut_guide_focus_return = self._shortcut_guide_focus_return, None
        if target is None:
            return
        workflow_id, held_view = target
        if self._interactive_view(workflow_id) is not held_view:
            held_view.external_output.focus(OwnedDialogClosed(restored=False))
            return

        def restore() -> None:
            if self._interactive_view(workflow_id) is not held_view:
                held_view.external_output.focus(OwnedDialogClosed(restored=False))
                return
            self._apply_transition_actions(
                workflow_id,
                held_view,
                held_view.external_output.focus(OwnedDialogClosed(restored=True)),
            )

        held_view.dialog.lifecycle.schedule(0, restore)

    def _apply_output_operation(self, result: OutputOperationResult) -> None:
        view = self._views.get(result.workflow_id)
        if view is None:
            return
        if not view.dialog.is_alive():
            self._evict_view(result.workflow_id, view)
            return
        self._apply_transition_actions(
            result.workflow_id,
            view,
            view.external_output.acknowledge(result),
        )

    def _apply_transition_actions(
        self,
        workflow_id: str,
        view: _SessionView,
        actions: tuple[PopupTransitionAction, ...],
    ) -> None:
        for action in actions:
            if isinstance(action, SetPopupVisibility):
                view.dialog.apply_external_output_visibility(action.visibility)
            elif isinstance(action, SetFocusProjection):
                view.surface.set_paste_focus_state(
                    action.focused,
                    self._paste_target,
                    voice_draft_editing=_voice_draft_editing(view),
                )
            elif isinstance(action, FocusPopup):
                focus_acquired = view.dialog.lifecycle.focus()
                if action.attention_id is not None:
                    self._command_sink(WorkflowAttentionCompleted(
                        action.attention_id,
                        workflow_id,
                        focus_acquired,
                    ))
            elif isinstance(action, ScheduleOutsideFocusCheck):
                self._schedule_outside_focus_check(workflow_id, view, action)
            elif isinstance(action, ReportControlSurfaceReleased):
                self._command_sink(ControlSurfaceReleased(ControlSurfaceRef(workflow_id, "workflow")))
            elif isinstance(action, RequestPopupClose):
                view.surface.collapse_overflow()
                self._request_close(workflow_id)
            elif isinstance(action, SetOutputActionEnabled):
                view.surface.set_standard_action_enabled(action.slot_id, action.enabled)
            elif isinstance(action, PulseOutputAction):
                pulse = (
                    view.surface.pulse_standard_action_error
                    if action.error
                    else view.surface.pulse_standard_action
                )
                pulse(action.slot_id)
            elif isinstance(action, ShowOutputMessage):
                if not action.only_when_overflow_collapsed or not view.surface.overflow_expanded:
                    view.surface.show_action_message(action.message, action.duration_ms)
                if action.warning:
                    view.dialog.flash("warning")

    def _schedule_outside_focus_check(
        self,
        workflow_id: str,
        scheduled_view: _SessionView,
        action: ScheduleOutsideFocusCheck,
    ) -> None:
        def check() -> None:
            view = self._views.get(workflow_id)
            if view is not scheduled_view:
                return
            try:
                focused = view.dialog.root.focus_get()
                focused_inside = focused is not None and focused.winfo_toplevel() is view.dialog.root
            except tk.TclError:
                focused_inside = False
            self._apply_transition_actions(
                workflow_id,
                view,
                view.external_output.focus(OutsideFocusObserved(
                    action.generation,
                    pinned=view.dialog.pinned,
                    focused_inside=focused_inside,
                )),
            )

        self._root.after(action.delay_ms, check)

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
        if self._shortcut_guide_dialog is not None:
            self._shortcut_guide_dialog.destroy()
            self._shortcut_guide_dialog = None
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
        point = self._pointer_press_reader.poll()
        if point is not None:
            self._handle_pointer_press(*point)
        while True:
            try:
                self._apply_paste_target(self._paste_target_updates.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                self._apply_output_operation(self._output_updates.get_nowait())
            except queue.Empty:
                break
        for snapshot in self._updates.drain():
            self._apply(snapshot)
        while True:
            try:
                self._apply_attention(self._attention_updates.get_nowait())
            except queue.Empty:
                break

    def _apply_attention(self, attention: WorkflowAttention) -> None:
        view = self._views.get(attention.workflow_id)
        if view is None or not view.dialog.is_alive():
            self._command_sink(WorkflowAttentionCompleted(
                attention.attention_id,
                attention.workflow_id,
                False,
            ))
            return
        self._apply_transition_actions(
            attention.workflow_id,
            view,
            view.external_output.attention(
                attention.attention_id,
                attention.message,
                duration_ms=attention.duration_ms,
                request_focus=attention.request_focus,
                warning=attention.warning,
            ),
        )

    def _handle_pointer_press(self, x: int, y: int) -> None:
        for workflow_id, view in tuple(self._views.items()):
            if not view.dialog.is_alive():
                self._evict_view(workflow_id, view)
                continue
            if not view.dialog.is_visible():
                continue
            if view.dialog.contains_screen_point(x, y):
                continue
            self._apply_transition_actions(
                workflow_id,
                view,
                view.external_output.focus(OutsidePointerPressed(pinned=view.dialog.pinned)),
            )

    def _apply_paste_target(self, target: PasteTarget | None) -> None:
        current = self._paste_target
        if target is not None and current is not None:
            if target.observation_sequence <= current.observation_sequence:
                return
        self._paste_target = target
        for view in self._views.values():
            view.surface.set_paste_focus_state(
                view.external_output.focused_inside,
                target,
                voice_draft_editing=_voice_draft_editing(view),
            )

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
        if view is None:
            view = self._create_view(snapshot.session_id)
            self._views[snapshot.session_id] = view
            self._register_view(snapshot.session_id, view)
        previous = view.last_snapshot
        if snapshot.status is SessionStatus.VOICE_REVIEW and (
            previous is None or previous.status is not SessionStatus.VOICE_REVIEW
        ):
            view.voice_draft_editing = True
        patch = workflow_render_patch(previous, snapshot)
        view.revision = snapshot.revision
        previous_step_id = view.step_id
        view.content = snapshot.content
        if snapshot.displayed_step_index >= 0:
            view.step_id = snapshot.steps[snapshot.displayed_step_index].step_id
        if previous_step_id is not None and view.step_id != previous_step_id:
            view.surface.close_feedback_overlay()
        if patch.header:
            view.surface.set_pinned_state(snapshot.pinned)
            view.surface.set_title(snapshot.title)
            view.surface.set_source_preview(snapshot.source_preview)
            view.surface.set_model(snapshot.model)
            view.surface.set_paste_focus_state(
                view.external_output.focused_inside,
                self._paste_target,
                voice_draft_editing=(
                    view.voice_draft_editing
                    if snapshot.status is SessionStatus.VOICE_REVIEW
                    else None
                ),
            )
            view.surface.configure_action_contract(snapshot.action_feedback_contract, snapshot.input_source)
        guidance_key = view.step_id or ""
        if snapshot.status == SessionStatus.COMPLETED and snapshot.show_guidance_hint and guidance_key not in view.shown_guidance_keys:
            view.shown_guidance_keys.add(guidance_key)
            view.surface.show_action_guidance_hint()
        if previous is None:
            view.surface.close_button.configure(
                command=lambda sid=snapshot.session_id: self._request_close(sid)
            )
            view.surface.pin_button.configure(
                command=lambda sid=snapshot.session_id: self._toggle_pin(sid)
            )
        if patch.header:
            view.surface.configure_back_action(
                (lambda sid=snapshot.session_id: self._command_sink(NavigateWorkflowBack(sid)))
                if snapshot.can_navigate_back
                else None
            )
        content_key = _content_render_key(snapshot)
        content_changed = patch.content
        if snapshot.status == SessionStatus.VOICE_REVIEW:
            origin = snapshot.voice_origin
            if origin is not None:
                view.voice_draft_revision = origin.revision

                def update_voice_draft(text: str, sid=snapshot.session_id, rendered=view) -> None:
                    expected_revision = rendered.voice_draft_revision
                    rendered.voice_draft_revision += 1
                    self._command_sink(UpdateVoiceDraft(sid, expected_revision, text))

                view.surface.set_editable_content(snapshot.content, update_voice_draft)
                view.surface.set_voice_draft_editing(view.voice_draft_editing)
        elif snapshot.status == SessionStatus.FAILED:
            view.dialog.flash("error")
            if content_changed:
                if snapshot.content:
                    if (
                        previous is not None
                        and previous.result_completeness == "partial"
                        and snapshot.result_completeness == "partial"
                        and snapshot.content.startswith(previous.content)
                    ):
                        view.surface.append_content_text(snapshot.content[len(previous.content):], "body")
                    else:
                        view.surface.set_content_chunks([(snapshot.content, "body")])
                    view.surface.set_source_preview(f"Failed: {snapshot.error}")
                else:
                    view.surface.set_content_chunks([(snapshot.error, "body")])
        elif snapshot.status in {SessionStatus.COMPLETED, SessionStatus.STOPPED}:
            if snapshot.status == SessionStatus.STOPPED:
                view.surface.show_action_message("已停止", 1000)
            completion_key = view.step_id or snapshot.content
            if snapshot.status == SessionStatus.COMPLETED and completion_key and completion_key not in view.flashed_completion_keys:
                view.flashed_completion_keys.add(completion_key)
                view.dialog.flash("success")
            if content_changed:
                if snapshot.presentation is not None:
                    view.surface.set_presentation_document(snapshot.presentation)
                elif snapshot.status == SessionStatus.STOPPED and not snapshot.content:
                    view.surface.set_content_chunks([("已停止", "body")])
                else:
                    view.surface.set_content_chunks([(snapshot.content, "body")])
        else:
            if content_changed:
                if snapshot.content:
                    if (
                        previous is not None
                        and previous.result_completeness == "partial"
                        and snapshot.result_completeness == "partial"
                        and snapshot.content.startswith(previous.content)
                    ):
                        view.surface.append_content_text(snapshot.content[len(previous.content):], "body")
                    else:
                        view.surface.set_content_chunks([(snapshot.content, "body")])
                    view.surface.set_source_preview(snapshot.status_text)
                else:
                    view.surface.set_loading(snapshot.status_text)
        if content_changed:
            view.rendered_content_key = content_key
        if patch.actions:
            view.surface.configure_standard_actions(
                on_speak=(lambda sid=snapshot.session_id: self._toggle_speech(sid)) if "speaker" in snapshot.available_actions else None,
                on_copy=(lambda sid=snapshot.session_id: self._copy(sid)) if "copy" in snapshot.available_actions else None,
                on_paste=(lambda sid=snapshot.session_id: self._paste(sid)) if "paste" in snapshot.available_actions else None,
                on_archive=(lambda sid=snapshot.session_id: self._archive(sid)) if "archive" in snapshot.available_actions else None,
                on_follow_up=(lambda sid=snapshot.session_id: self._toggle_follow_up(sid)) if "follow_up" in snapshot.available_actions else None,
            )
        self._configure_voice_capture_controls(snapshot, view)
        view.speaking = snapshot.speaking
        if patch.visual_state:
            view.surface.set_speaker_active(snapshot.speaking)
        if patch.feedback and snapshot.status == SessionStatus.COMPLETED and snapshot.action_feedback_contract is not None and view.step_id is not None:
            view.surface.configure_feedback(
                snapshot.action_feedback_contract,
                snapshot.feedback_state,
                snapshot.feedback_message,
                lambda outcome, reason, note, save_case, sid=snapshot.session_id, step=view.step_id: self._submit_feedback(
                    sid, step, outcome, reason, note, save_case
                ),
            )
        elif patch.feedback:
            view.surface.hide_feedback()
        if (
            previous is not None
            and previous.status in {SessionStatus.VOICE_LISTENING, SessionStatus.VOICE_FINALIZING}
            and snapshot.status is SessionStatus.VOICE_REVIEW
        ):
            self._schedule_initial_focus(snapshot.session_id, view)
        view.last_snapshot = snapshot

    def _evict_view(self, session_id: str, view: _SessionView) -> None:
        if self._views.get(session_id) is view:
            self._views.pop(session_id, None)

    def _request_close(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None or view.close_requested:
            return
        view.close_requested = True
        self._command_sink(CloseSession(session_id))

    def _interactive_view(self, session_id: str) -> _SessionView | None:
        view = self._views.get(session_id)
        if view is None or view.close_requested or not view.dialog.is_alive():
            return None
        return view

    def _send_text_command(self, session_id: str, command_type) -> None:
        view = self._interactive_view(session_id)
        if view is not None:
            self._command_sink(command_type(session_id, view.surface.selected_text()))

    def _copy(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        operation_id = uuid.uuid4().hex
        view.external_output.begin("copy", operation_id)
        text = view.surface.selected_text()
        self._command_sink(CopyResult(session_id, text, operation_id))

    def _toggle_speech(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        text = view.surface.selected_text()
        operation_id = uuid.uuid4().hex
        if not view.speaking:
            view.external_output.begin("speech", operation_id)
        self._command_sink(ToggleSpeech(session_id, text, operation_id))

    def _archive(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        operation_id = uuid.uuid4().hex
        view.external_output.begin("archive", operation_id)
        self._command_sink(ArchiveResult(session_id, view.surface.selected_text(), operation_id))

    def _paste(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        operation_id = uuid.uuid4().hex
        text = view.surface.selected_text()
        if view.last_snapshot is not None and view.last_snapshot.status is SessionStatus.VOICE_REVIEW:
            text = text if text is not None else view.surface.semantic_content()
        transition = view.external_output.begin(
            "paste",
            operation_id,
            pinned=view.dialog.pinned,
        )
        if not transition.accepted:
            return
        self._apply_transition_actions(session_id, view, transition.actions)
        self._command_sink(PasteResult(session_id, text, operation_id))

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
            height=bounds.height if bounds else 336,
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
            on_close_request=lambda sid=session_id: self._request_close(sid),
        )
        surface = BaseResultSurface(dialog)
        surface.configure_standard_actions()
        stop = surface.add_action_slot("voice_stop", "Stop", None, width=46, tooltip="Stop Voice Input")
        cancel = surface.add_action_slot("voice_cancel", "Cancel", None, width=54, tooltip="Cancel Voice Input")
        stop.pack_forget()
        cancel.pack_forget()
        return _SessionView(dialog=dialog, surface=surface, voice_stop_button=stop, voice_cancel_button=cancel)

    def _configure_voice_capture_controls(self, snapshot: SessionSnapshot, view: _SessionView) -> None:
        capture_id = snapshot.voice_capture_id
        stop, cancel = view.voice_stop_button, view.voice_cancel_button
        if stop is None or cancel is None:
            return
        listening = snapshot.status is SessionStatus.VOICE_LISTENING and capture_id is not None
        finalizing = snapshot.status is SessionStatus.VOICE_FINALIZING and capture_id is not None
        if listening:
            stop.configure(command=lambda cid=capture_id: self._command_sink(StopVoiceCapture(cid)), state="normal")
            if not stop.winfo_manager(): stop.pack(side="left", padx=(0, 5))
        else:
            stop.pack_forget()
        if listening or finalizing:
            cancel.configure(command=lambda cid=capture_id: self._command_sink(CancelVoiceCapture(cid)), state="normal")
            if not cancel.winfo_manager(): cancel.pack(side="left", padx=(0, 5))
        else:
            cancel.pack_forget()

    def _register_view(
        self,
        session_id: str,
        view: _SessionView,
        *,
        focus_on_show: bool = True,
    ) -> None:
        view.external_output.focus(PopupRegistered())
        dialog = view.dialog
        toggle_voice_draft_mode = lambda event, sid=session_id: self._popup_shortcut(
            event,
            self._toggle_voice_draft_mode,
            sid,
        )
        dialog.root.bind("<FocusOut>", lambda _event, sid=session_id: self._close_if_outside(sid), add="+")
        dialog.root.bind("<FocusIn>", lambda _event, sid=session_id: self._focus_in(sid), add="+")
        dialog.root.bind("<ButtonPress>", lambda _event, sid=session_id: self._activate(sid), add="+")
        dialog.root.bind("<Control-q>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_speech, sid), add="+")
        dialog.root.bind("<Control-e>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_pin, sid), add="+")
        dialog.root.bind("<Control-c>", lambda event, sid=session_id: self._popup_shortcut(event, self._copy, sid), add="+")
        dialog.root.bind("<Control-s>", lambda event, sid=session_id: self._popup_shortcut(event, self._archive, sid), add="+")
        dialog.root.bind("<Control-r>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_feedback, sid), add="+")
        dialog.root.bind("<Control-v>", lambda event, sid=session_id: self._paste_shortcut(event, sid), add="+")
        dialog.root.bind("<Control-Return>", toggle_voice_draft_mode, add="+")
        dialog.root.bind("<Control-KP_Enter>", toggle_voice_draft_mode, add="+")
        dialog.root.bind("<Control-slash>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_follow_up, sid), add="+")
        view.surface.bind_header_double_click(lambda _event, sid=session_id: self._header_double_click(sid))
        view.surface.bind_voice_draft_mode_toggle(toggle_voice_draft_mode)
        view.external_output.focus(PopupShown())
        if focus_on_show:
            self._schedule_initial_focus(session_id, view)

    def _schedule_initial_focus(self, session_id: str, view: _SessionView) -> None:
        def establish_initial_focus() -> None:
            if self._views.get(session_id) is not view or view.external_output.focused_inside:
                return
            if not view.surface.focus_content():
                return
            self._apply_transition_actions(
                session_id,
                view,
                view.external_output.focus(FocusEntered()),
            )

        view.dialog.lifecycle.schedule(0, establish_initial_focus)

    def _shortcut(self, action: Callable[[str], None], session_id: str) -> str:
        view = self._views.get(session_id)
        if view is not None and view.external_output.focused_inside:
            action(session_id)
        return "break"

    def _popup_shortcut(self, event, action: Callable[[str], None], session_id: str) -> str:
        if _has_only_popup_shortcut_modifiers(event):
            return self._shortcut(action, session_id)
        return "break"

    def _paste_shortcut(self, event, session_id: str) -> str | None:
        if not _has_only_popup_shortcut_modifiers(event):
            return "break"
        if _accepts_native_paste(getattr(event, "widget", None)):
            return None
        view = self._views.get(session_id)
        if view is not None and view.last_snapshot is not None and view.last_snapshot.status is SessionStatus.VOICE_REVIEW:
            return self._shortcut(self._paste, session_id)
        return self._shortcut(self._paste, session_id)

    def _toggle_voice_draft_mode(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None or view.last_snapshot is None or view.last_snapshot.status is not SessionStatus.VOICE_REVIEW:
            return
        view.voice_draft_editing = not view.voice_draft_editing
        view.surface.set_voice_draft_editing(view.voice_draft_editing)
        view.surface.set_paste_focus_state(
            view.external_output.focused_inside,
            self._paste_target,
            voice_draft_editing=view.voice_draft_editing,
        )

    def _header_double_click(self, session_id: str) -> str:
        self._toggle_pin(session_id)
        return "break"

    def _focus_in(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        self._apply_transition_actions(
            session_id,
            view,
            view.external_output.focus(FocusEntered()),
        )
        self._command_sink(ControlSurfaceActivated(ControlSurfaceRef(session_id, "workflow")))
        self._activate(session_id)

    def _activate(self, session_id: str) -> None:
        self._command_sink(ActivateWorkflow(session_id))

    def _close_if_outside(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        self._apply_transition_actions(
            session_id,
            view,
            view.external_output.focus(OutsideFocusCheckRequested()),
        )


def _voice_draft_editing(view: _SessionView) -> bool | None:
    snapshot = view.last_snapshot
    return (
        view.voice_draft_editing
        if snapshot is not None and snapshot.status is SessionStatus.VOICE_REVIEW
        else None
    )


def _content_render_key(snapshot: SessionSnapshot) -> tuple[object, ...]:
    """Only content-affecting state may replace the textbox and reset its scroll."""
    if snapshot.status == SessionStatus.FAILED:
        return (snapshot.status, snapshot.content, snapshot.error)
    if snapshot.status == SessionStatus.COMPLETED:
        return (snapshot.status, snapshot.content, snapshot.presentation)
    if snapshot.status == SessionStatus.STOPPED:
        return (snapshot.status, snapshot.content, snapshot.status_text, snapshot.presentation)
    return (snapshot.status, snapshot.content, snapshot.status_text, snapshot.presentation)


def workflow_render_patch(previous: SessionSnapshot | None, current: SessionSnapshot) -> WorkflowRenderPatch:
    if previous is None:
        return WorkflowRenderPatch(True, True, True, True, True)
    previous_step = _displayed_step_id(previous)
    current_step = _displayed_step_id(current)
    return WorkflowRenderPatch(
        header=(
            previous.pinned,
            previous.title,
            previous.source_preview,
            previous.model,
            previous.can_navigate_back,
            previous.action_feedback_contract,
            previous.input_source,
        ) != (
            current.pinned,
            current.title,
            current.source_preview,
            current.model,
            current.can_navigate_back,
            current.action_feedback_contract,
            current.input_source,
        ),
        content=_content_render_key(previous) != _content_render_key(current),
        actions=previous.available_actions != current.available_actions,
        feedback=(
            previous_step,
            previous.action_feedback_contract,
            previous.feedback_state,
            previous.feedback_message,
            previous.status == SessionStatus.COMPLETED,
        ) != (
            current_step,
            current.action_feedback_contract,
            current.feedback_state,
            current.feedback_message,
            current.status == SessionStatus.COMPLETED,
        ),
        visual_state=previous.speaking != current.speaking,
    )


def _displayed_step_id(snapshot: SessionSnapshot) -> str | None:
    if 0 <= snapshot.displayed_step_index < len(snapshot.steps):
        return snapshot.steps[snapshot.displayed_step_index].step_id
    return None


def _has_only_popup_shortcut_modifiers(event: object | None) -> bool:
    """Allow Ctrl with lock-state bits, but not Alt, Shift, or other modifiers."""
    state = getattr(event, "state", 0)
    return isinstance(state, int) and state & ~_POPUP_SHORTCUT_ALLOWED_MODIFIERS == 0


def _accepts_native_paste(widget: object | None) -> bool:
    if widget is None:
        return False
    try:
        return widget.winfo_class() in {"Entry", "TEntry", "Text", "Spinbox"} and str(widget.cget("state")) == "normal"  # type: ignore[attr-defined]
    except (AttributeError, tk.TclError):
        return False
