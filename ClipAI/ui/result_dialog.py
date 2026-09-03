from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import queue
import threading
import tkinter as tk
import uuid
import webbrowser

import customtkinter as ctk

from ClipAI.core.commands import ArchiveResult, CloseSession, CopyResult, FollowUp, NavigateWorkflowBack, PasteResult, StartPopupVoiceCapture, StopVoiceCapture, SubmitActionFeedback, SubmitContextualQuestion, TogglePin, ToggleSpeech, UpdateVoiceDraft, WorkflowAttentionCompleted
from ClipAI.core.models import ActiveWorkflowContext, EntryPanelSnapshot, FeedbackOutcome, OutputOperationResult, PasteTarget, PersonalStyleState, PopupBounds, ProviderSettingsState, ShortcutGuideSnapshot, WorkflowAttention
from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface, PointerPressReader
from ClipAI.core.popup_presentation import project_popup_presentation
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceCaptureId, VoiceCapturePhase, VoiceCaptureSurfaceContext, VoiceProjection
from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface
from ClipAI.ui.popup_control import PopupControl, PopupControlRegistered, PopupControlShown, PopupForegroundPolled, PopupInsidePointerPressed, PopupOutsideFocusRequested, PopupOutsidePointerPressed, PopupOwnedDialogClosed, PopupOwnedDialogOpened, PopupProjectionContext, ToolkitFocusEntered
from ClipAI.ui.popup_layout import PopupLayoutPolicy
from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceLease, PrimarySurfaceSpec
from ClipAI.ui.provider_settings import ProviderSettingsDialog
from ClipAI.ui.personal_styles import PersonalStylesDialog
from ClipAI.ui.shortcut_guide import ShortcutGuideDialog
from ClipAI.ui.unified_entry_panel import UnifiedEntryPanelDialog
from ClipAI.ui.voice_setup import VoiceSetupDialog
from ClipAI.ui.about import AboutDialog


# Windows Tk maps Num Lock to Mod1 (0x0008), while physical Alt uses
# the separate 0x00020000 state bit. Lock states must not disable Ctrl shortcuts.
_POPUP_SHORTCUT_ALLOWED_MODIFIERS = 0x0002 | 0x0004 | 0x0008 | 0x0010


def _voice_status_word(
    phase: VoiceCapturePhase | None,
    *,
    silence_detected: bool,
) -> str:
    if phase in {
        VoiceCapturePhase.STOP_REQUESTED,
        VoiceCapturePhase.FINALIZING,
        VoiceCapturePhase.CANCEL_REQUESTED,
    }:
        return "整理"
    if phase is None:
        return "語音"
    if silence_detected:
        return "無聲"
    return "聆聽"


@dataclass
class _SessionView:
    dialog: BaseDialog
    surface: BaseResultSurface
    revision: int = -1
    speaking: bool = False
    content: str = ""
    step_id: str | None = None
    popup_control: PopupControl | None = None
    flashed_completion_keys: set[str] = field(default_factory=set)
    rendered_content_key: tuple[object, ...] | None = None
    shown_guidance_keys: set[str] = field(default_factory=set)
    close_requested: bool = False
    last_snapshot: SessionSnapshot | None = None
    voice_draft_revision: int = 0
    applied_voice_insertion_revision: int | None = None
    voice_draft_editing: bool = True
    applied_follow_up_capture_ids: set[str] = field(default_factory=set)


@dataclass
class _PrimaryEntrySurface:
    dialog: UnifiedEntryPanelDialog
    host: PrimarySurfaceHost
    panel_lease: PrimarySurfaceLease
    workflow_id: str | None = None


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
        native_window_surface: NativeWindowSurface | None = None,
        focus_transition_diagnostics: bool = False,
        voice_projection: VoiceProjection | None = None,
        application_version: str = "development",
        github_url: str = "https://github.com/yomingpan/clipai",
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
        self._pointer_press_reader = pointer_press_reader
        self._native_window_surface = native_window_surface
        self._focus_transition_diagnostics = focus_transition_diagnostics
        self._provider_settings_dialog: ProviderSettingsDialog | None = None
        self._personal_styles_dialog: PersonalStylesDialog | None = None
        self._shortcut_guide_dialog: ShortcutGuideDialog | None = None
        self._entry_panel_dialog: UnifiedEntryPanelDialog | None = None
        self._primary_entry_surface: _PrimaryEntrySurface | None = None
        self._shortcut_guide_focus_hold_active = False
        self._shortcut_guide_focus_return: tuple[str, _SessionView] | None = None
        self._voice_setup_dialog: VoiceSetupDialog | None = None
        self._voice_projection = voice_projection
        self._application_version = application_version
        self._github_url = github_url
        self._about_dialog: AboutDialog | None = None

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

    def voice_capture_surface_context(self, workflow_id: str) -> VoiceCaptureSurfaceContext | None:
        view = self._interactive_view(workflow_id)
        if view is None or view.last_snapshot is None:
            return None
        selection = (
            view.surface.selection_range()
            if view.last_snapshot.status is SessionStatus.VOICE_REVIEW
            else None
        )
        return VoiceCaptureSurfaceContext(
            workflow_id,
            follow_up_requested=view.surface.follow_up_visible,
            selection=selection,
        )

    def render(self, snapshot: SessionSnapshot) -> None:
        self._updates.put(snapshot)

    def present_output_operation(self, result: OutputOperationResult) -> None:
        self._output_updates.put(result)

    def present_paste_target(self, target: PasteTarget | None) -> None:
        self._paste_target_updates.put(target)

    def present_workflow_attention(self, attention: WorkflowAttention) -> None:
        self._attention_updates.put(attention)

    def present_entry_panel(self, snapshot: EntryPanelSnapshot | None) -> None:
        if snapshot is None:
            primary_entry = self._primary_entry_surface
            if primary_entry is not None:
                if not primary_entry.host.restore(primary_entry.panel_lease):
                    primary_entry.host.close(primary_entry.panel_lease)
                primary_entry.dialog.close()
                self._primary_entry_surface = None
                self._entry_panel_dialog = None
                self._restore_focus_after_owned_surface()
                return
            if self._entry_panel_dialog is not None:
                self._entry_panel_dialog.close()
                self._entry_panel_dialog = None
            self._restore_focus_after_owned_surface()
            return
        if self._native_window_surface is None or self._display_metrics is None:
            return
        self._hold_focus_for_owned_surface()
        anchor = self._owned_popup_bounds()
        if self._entry_panel_dialog is None:
            held = self._shortcut_guide_focus_return
            held_view = held[1] if held is not None else None
            host = (
                held_view.dialog.primary_surface_host
                if held_view is not None
                else None
            )
            active_lease = (
                held_view.dialog.primary_surface_lease
                if held_view is not None
                else None
            )
            if host is None or active_lease is None:
                bounds = anchor or self._layout_policy.calculate(
                    self._display_metrics.current()
                )
                host = PrimarySurfaceHost(
                    self._root,
                    PrimarySurfaceSpec(bounds),
                    self._native_window_surface,
                )
            panel_lease = host.acquire()
            dialog = UnifiedEntryPanelDialog(
                self._root,
                self._command_sink,
                self._native_window_surface,
                self._display_metrics,
                self._layout_policy,
                primary_surface_host=host,
                primary_surface_lease=panel_lease,
            )
            dialog.apply(snapshot)
            mounted = (
                host.replace(active_lease, panel_lease, dialog)
                if active_lease is not None
                else host.mount(panel_lease, dialog)
            )
            if not mounted:
                host.close()
                self._restore_focus_after_owned_surface()
                return
            self._entry_panel_dialog = dialog
            self._primary_entry_surface = _PrimaryEntrySurface(
                dialog,
                host,
                panel_lease,
            )
            if active_lease is None:
                if snapshot.status == "preparing":
                    host.apply_visibility("visible_no_activate")
                else:
                    host.show(panel_lease)
            dialog.reveal()
            return
        self._entry_panel_dialog.show(snapshot, anchor=anchor)

    def transition_entry_panel_to_popup(
        self,
        panel_id: str,
        workflow_id: str,
    ) -> None:
        """Keep the Panel visible until its admitted Popup is ready to replace it."""
        dialog = self._entry_panel_dialog
        if dialog is None:
            return
        primary_entry = getattr(self, "_primary_entry_surface", None)
        if primary_entry is not None and dialog.presents(panel_id):
            primary_entry.workflow_id = workflow_id

    def show_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is None:
            if self._native_window_surface is None:
                return
            self._provider_settings_dialog = ProviderSettingsDialog(
                self._root,
                self._command_sink,
                self._native_window_surface,
            )
        self._provider_settings_dialog.apply(state)

    def set_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.apply(state)

    def close_provider_settings(self) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.close()

    def show_personal_styles(self, state: PersonalStyleState) -> None:
        if self._personal_styles_dialog is None:
            if self._native_window_surface is None:
                return
            self._personal_styles_dialog = PersonalStylesDialog(
                self._root,
                self._command_sink,
                self._native_window_surface,
            )
        self._personal_styles_dialog.apply(state)

    def set_personal_styles(self, state: PersonalStyleState) -> None:
        if self._personal_styles_dialog is not None:
            self._personal_styles_dialog.apply(state)

    def close_personal_styles(self) -> None:
        if self._personal_styles_dialog is not None:
            self._personal_styles_dialog.close()

    def show_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None:
        self._hold_focus_for_shortcut_guide()
        if self._shortcut_guide_dialog is None:
            if self._native_window_surface is None:
                return
            self._shortcut_guide_dialog = ShortcutGuideDialog(
                self._root,
                self._command_sink,
                self._native_window_surface,
            )
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

    def show_about(self) -> None:
        if self._native_window_surface is None:
            return
        if self._about_dialog is None:
            self._about_dialog = AboutDialog(
                self._root,
                self._command_sink,
                self._native_window_surface,
                version=self._application_version,
                github_url=self._github_url,
            )

    def close_about(self) -> None:
        if self._about_dialog is not None:
            self._about_dialog.close()
            self._about_dialog = None

    def open_github(self, url: str) -> None:
        webbrowser.open(url)

    def set_voice_projection(self, projection: VoiceProjection) -> None:
        self._voice_projection = projection
        if self._voice_setup_dialog is not None:
            self._voice_setup_dialog.set_voice_projection(projection)
        for view in self._views.values():
            if view.last_snapshot is not None:
                self._configure_voice_control(view.last_snapshot, view)

    def _hold_focus_for_shortcut_guide(self) -> None:
        self._hold_focus_for_owned_surface()

    def _hold_focus_for_owned_surface(self) -> None:
        if self._shortcut_guide_focus_hold_active:
            return
        self._shortcut_guide_focus_hold_active = True
        self._shortcut_guide_focus_return = None
        for workflow_id, view in self._views.items():
            if (
                self._interactive_view(workflow_id) is not view
                or not self._popup_control(workflow_id, view).owns_focus
            ):
                continue
            self._popup_control(workflow_id, view).observe_focus(PopupOwnedDialogOpened())
            self._shortcut_guide_focus_return = (workflow_id, view)
            return

    def _owned_popup_bounds(self) -> PopupBounds | None:
        target = self._shortcut_guide_focus_return
        if target is None:
            return None
        workflow_id, held_view = target
        if self._interactive_view(workflow_id) is not held_view:
            return None
        return held_view.dialog.current_bounds()

    def _restore_focus_after_shortcut_guide(self) -> None:
        self._restore_focus_after_owned_surface()

    def _restore_focus_after_owned_surface(self) -> None:
        if not self._shortcut_guide_focus_hold_active:
            return
        self._shortcut_guide_focus_hold_active = False
        target, self._shortcut_guide_focus_return = self._shortcut_guide_focus_return, None
        if target is None:
            return
        workflow_id, held_view = target
        if self._interactive_view(workflow_id) is not held_view:
            self._popup_control(workflow_id, held_view).observe_focus(
                PopupOwnedDialogClosed(restored=False)
            )
            return

        def restore() -> None:
            if self._interactive_view(workflow_id) is not held_view:
                self._popup_control(workflow_id, held_view).observe_focus(
                    PopupOwnedDialogClosed(restored=False)
                )
                return
            self._popup_control(workflow_id, held_view).observe_focus(
                PopupOwnedDialogClosed(restored=True)
            )

        held_view.dialog.lifecycle.schedule(0, restore)

    def _apply_output_operation(self, result: OutputOperationResult) -> None:
        view = self._views.get(result.workflow_id)
        if view is None:
            return
        if not view.dialog.is_alive():
            self._close_dead_view(result.workflow_id, view)
            return
        self._popup_control(result.workflow_id, view).settle_output(result)

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
            if view.popup_control is not None:
                view.popup_control.dispose()
            view.dialog.close()
        self._views.clear()
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.destroy()
            self._provider_settings_dialog = None
        if self._personal_styles_dialog is not None:
            self._personal_styles_dialog.destroy()
            self._personal_styles_dialog = None
        if self._shortcut_guide_dialog is not None:
            self._shortcut_guide_dialog.destroy()
            self._shortcut_guide_dialog = None
        if self._entry_panel_dialog is not None:
            primary_entry = self._primary_entry_surface
            if primary_entry is not None:
                primary_entry.host.close()
                self._primary_entry_surface = None
            self._entry_panel_dialog.close()
            self._entry_panel_dialog = None
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
        for workflow_id, view in tuple(self._views.items()):
            if not view.dialog.is_alive():
                self._close_dead_view(workflow_id, view)
                continue
            if view.dialog.is_visible():
                self._popup_control(workflow_id, view).observe_focus(PopupForegroundPolled())
        point = self._pointer_press_reader.poll() if self._pointer_press_reader is not None else None
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
        self._popup_control(attention.workflow_id, view).present_attention(attention)

    def _handle_pointer_press(self, x: int, y: int) -> None:
        entry_panel = getattr(self, "_entry_panel_dialog", None)
        if entry_panel is not None and not entry_panel.contains_screen_point(x, y):
            entry_panel.request_close()
        for workflow_id, view in tuple(self._views.items()):
            if not view.dialog.is_alive():
                self._close_dead_view(workflow_id, view)
                continue
            if not view.dialog.is_visible():
                continue
            if view.dialog.contains_screen_point(x, y):
                continue
            self._popup_control(workflow_id, view).observe_focus(PopupOutsidePointerPressed())

    def _apply_paste_target(self, target: PasteTarget | None) -> None:
        current = self._paste_target
        if target is not None and current is not None:
            if target.observation_sequence <= current.observation_sequence:
                return
        self._paste_target = target
        for workflow_id, view in self._views.items():
            self._project_popup_context(workflow_id, view)

    def _apply(self, snapshot: SessionSnapshot) -> None:
        view = self._views.get(snapshot.session_id)
        if view is not None and not view.dialog.is_alive():
            self._close_dead_view(snapshot.session_id, view)
            return
        if view is not None and snapshot.revision <= view.revision:
            return
        if snapshot.status in {SessionStatus.CLOSED, SessionStatus.CANCELLED}:
            if view is not None:
                view.dialog.close()
                self._evict_view(snapshot.session_id, view)
            return
        primary_entry = getattr(self, "_primary_entry_surface", None)
        primary_transition = (
            primary_entry
            if primary_entry is not None
            and primary_entry.workflow_id == snapshot.session_id
            else None
        )
        if view is None:
            if primary_transition is not None:
                result_lease = primary_transition.host.acquire()
                view = self._create_view(
                    snapshot.session_id,
                    bounds=primary_transition.host.current_bounds(),
                    show_on_create=False,
                    primary_host=primary_transition.host,
                    primary_lease=result_lease,
                    mount_primary_content=False,
                )
            else:
                view = self._create_view(snapshot.session_id)
            self._views[snapshot.session_id] = view
            if primary_transition is not None:
                self._register_view(
                    snapshot.session_id,
                    view,
                    focus_on_show=False,
                    announce_shown=False,
                )
            else:
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
        view.step_id = _displayed_step_id(snapshot)
        if previous_step_id is not None and view.step_id != previous_step_id:
            view.surface.close_feedback_overlay()
        guidance_key = view.step_id or ""
        popup_model = project_popup_presentation(
            snapshot,
            guidance_already_shown=guidance_key in view.shown_guidance_keys,
        )
        view.surface.render(popup_model)
        if popup_model.guidance:
            view.shown_guidance_keys.add(guidance_key)
        if patch.header:
            self._project_popup_context(snapshot.session_id, view)
        content_key = _content_render_key(snapshot)
        content_changed = patch.content
        if snapshot.status == SessionStatus.VOICE_REVIEW:
            origin = snapshot.voice_origin
            if origin is not None:
                view.voice_draft_revision = origin.revision
                insertion = origin.latest_insertion
                caret_offset = None
                if (
                    insertion is not None
                    and insertion.projection_revision != view.applied_voice_insertion_revision
                ):
                    caret_offset = insertion.end

                def update_voice_draft(text: str, sid=snapshot.session_id, rendered=view) -> None:
                    expected_revision = rendered.voice_draft_revision
                    rendered.voice_draft_revision += 1
                    self._command_sink(UpdateVoiceDraft(sid, expected_revision, text))

                view.surface.set_editable_content(
                    snapshot.content,
                    update_voice_draft,
                    caret_offset=caret_offset,
                )
                if insertion is not None and caret_offset is not None:
                    view.applied_voice_insertion_revision = insertion.projection_revision
                view.surface.set_voice_draft_editing(view.voice_draft_editing)
                if not snapshot.content and snapshot.status_text:
                    view.dialog.flash("warning")
                    view.surface.show_action_message(snapshot.status_text, 4000)
        elif snapshot.status is SessionStatus.CONTEXT_QUESTION:
            if content_changed:
                view.surface.set_content_chunks([])
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
                else:
                    view.surface.set_loading(snapshot.status_text)
        if content_changed:
            view.rendered_content_key = content_key
        if (
            snapshot.question_composer_revision
            and (
                previous is None
                or snapshot.question_composer_revision != previous.question_composer_revision
            )
        ):
            self._show_follow_up(snapshot.session_id)
        insertion = snapshot.voice_follow_up_insertion
        if (
            snapshot.voice_capture_id is not None
            and snapshot.status is not SessionStatus.VOICE_REVIEW
            and "follow_up" in snapshot.available_actions
            and not view.surface.follow_up_visible
        ):
            self._show_follow_up(snapshot.session_id)
        if insertion is not None and insertion.capture_id not in view.applied_follow_up_capture_ids:
            view.applied_follow_up_capture_ids.add(insertion.capture_id)
            view.surface.insert_follow_up_text(insertion.text)
            view.surface.set_follow_up_active(True)
        self._configure_voice_control(snapshot, view)
        view.speaking = snapshot.speaking
        if (
            previous is not None
            and previous.status in {SessionStatus.VOICE_LISTENING, SessionStatus.VOICE_FINALIZING}
            and snapshot.status is SessionStatus.VOICE_REVIEW
        ):
            self._schedule_initial_focus(snapshot.session_id, view)
        view.last_snapshot = snapshot
        if primary_transition is not None:
            self._complete_primary_entry_transition(
                snapshot.session_id,
                view,
                primary_transition,
            )
            return

    def _complete_primary_entry_transition(
        self,
        workflow_id: str,
        view: _SessionView,
        transition: _PrimaryEntrySurface,
    ) -> bool:
        result_host = view.dialog.primary_surface_host
        result_lease = view.dialog.primary_surface_lease
        if (
            result_host is not transition.host
            or result_lease is None
            or not transition.host.replace(
                transition.panel_lease,
                result_lease,
                view.dialog,
            )
        ):
            return False
        transition.dialog.close()
        self._entry_panel_dialog = None
        self._primary_entry_surface = None
        self._restore_focus_after_owned_surface()
        self._popup_control(workflow_id, view).observe_focus(PopupControlShown())
        self._schedule_initial_focus(workflow_id, view)
        return True

    def _evict_view(self, session_id: str, view: _SessionView) -> None:
        if self._views.get(session_id) is view:
            if view.popup_control is not None:
                view.popup_control.dispose()
            self._views.pop(session_id, None)

    def _close_dead_view(self, session_id: str, view: _SessionView) -> None:
        if self._views.get(session_id) is not view:
            return
        self._request_close(session_id)
        self._evict_view(session_id, view)

    def _request_close(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None or view.close_requested:
            return
        view.close_requested = True
        self._command_sink(CloseSession(session_id))

    def _interactive_view(self, session_id: str) -> _SessionView | None:
        view = self._views.get(session_id)
        if (
            view is None
            or view.close_requested
            or not view.dialog.is_alive()
            or not view.dialog.is_visible()
        ):
            return None
        return view

    def _popup_control(self, workflow_id: str, view: _SessionView) -> PopupControl:
        control = view.popup_control
        if control is None:
            control = PopupControl(
                workflow_id,
                view.dialog,
                view.surface,
                command_sink=lambda command: self._command_sink(command),
                request_close=lambda: self._request_close(workflow_id),
                projection_context=PopupProjectionContext(
                    self._paste_target,
                    _voice_draft_editing(view),
                ),
                diagnostics=self._focus_transition_diagnostics,
            )
            view.popup_control = control
        return control

    def _project_popup_context(self, workflow_id: str, view: _SessionView) -> None:
        context = PopupProjectionContext(
            self._paste_target,
            _voice_draft_editing(view),
        )
        self._popup_control(workflow_id, view).update_projection_context(context)

    def _send_text_command(self, session_id: str, command_type) -> None:
        view = self._interactive_view(session_id)
        if view is not None:
            self._command_sink(command_type(session_id, view.surface.selected_text()))

    def _copy(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        operation_id = self._popup_control(session_id, view).begin_output("copy")
        if operation_id is None:
            return
        text = view.surface.selected_text()
        self._command_sink(CopyResult(session_id, text, operation_id))

    def _toggle_speech(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        text = view.surface.selected_text()
        operation_id = uuid.uuid4().hex
        if not view.speaking:
            operation_id = self._popup_control(session_id, view).begin_output("speech")
            if operation_id is None:
                return
        self._command_sink(ToggleSpeech(session_id, text, operation_id))

    def _archive(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        operation_id = self._popup_control(session_id, view).begin_output("archive")
        if operation_id is None:
            return
        self._command_sink(ArchiveResult(session_id, view.surface.selected_text(), operation_id))

    def _paste(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        text = view.surface.selected_text()
        if view.last_snapshot is not None and view.last_snapshot.status is SessionStatus.VOICE_REVIEW:
            text = text if text is not None else view.surface.semantic_content()
        operation_id = self._popup_control(session_id, view).begin_output(
            "paste",
            pinned=view.dialog.pinned,
        )
        if operation_id is None:
            return
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
        if view.last_snapshot is not None and view.last_snapshot.voice_capture_id is not None:
            view.surface.show_action_message("請先停止語音輸入", 1500)
            return
        if view.surface.follow_up_visible:
            view.surface.hide_follow_up()
            view.surface.set_follow_up_active(False)
            return
        self._show_follow_up(session_id)

    def _show_follow_up(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        view.surface.show_follow_up()
        view.surface.set_follow_up_active(True)

        def send() -> None:
            if view.last_snapshot is not None and view.last_snapshot.voice_capture_id is not None:
                return
            question = view.surface.follow_entry.get().strip()
            if question:
                view.surface.clear_follow_up_text()
                view.surface.hide_follow_up()
                view.surface.set_follow_up_active(False)
                if (
                    view.last_snapshot is not None
                    and view.last_snapshot.status is SessionStatus.CONTEXT_QUESTION
                ):
                    self._command_sink(SubmitContextualQuestion(session_id, question))
                else:
                    self._command_sink(FollowUp(session_id, question))

        view.surface.follow_send_button.configure(command=send)
        view.surface.follow_entry.bind("<Return>", lambda _event: send(), add="+")
        view.surface.follow_entry.bind(
            "<KeyRelease>",
            lambda _event, sid=session_id: self._refresh_follow_up_send(sid),
            add="+",
        )
        self._refresh_follow_up_send(session_id)

    def _refresh_follow_up_send(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None:
            return
        capture_active = (
            view.last_snapshot is not None
            and view.last_snapshot.voice_capture_id is not None
        )
        view.surface.set_follow_up_send_enabled(
            not capture_active and bool(view.surface.follow_entry.get().strip())
        )

    def _create_view(
        self,
        session_id: str,
        *,
        bounds: PopupBounds | None = None,
        show_on_create: bool = True,
        primary_host: PrimarySurfaceHost | None = None,
        primary_lease: PrimarySurfaceLease | None = None,
        mount_primary_content: bool = True,
    ) -> _SessionView:
        if bounds is None:
            metrics = (
                self._display_metrics.current()
                if self._display_metrics is not None
                else None
            )
            bounds = self._layout_policy.calculate(metrics) if metrics is not None else None
        if primary_host is None:
            bounds = bounds or PopupBounds(20, 20, 400, 336)
            primary_host = PrimarySurfaceHost(
                self._root,
                PrimarySurfaceSpec(bounds),
                self._native_window_surface,
            )
            primary_lease = primary_host.acquire()
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
            show_on_create=show_on_create if primary_host is None else False,
            on_close_request=lambda sid=session_id: self._request_close(sid),
            native_window_surface=self._native_window_surface,
            primary_surface_host=primary_host,
            primary_surface_lease=primary_lease,
            mount_primary_content=mount_primary_content,
        )
        surface = BaseResultSurface(dialog)
        view = _SessionView(dialog=dialog, surface=surface)
        surface.close_button.configure(
            command=lambda sid=session_id: self._request_close(sid)
        )
        surface.pin_button.configure(
            command=lambda sid=session_id: self._toggle_pin(sid)
        )
        surface.bind_back_action(
            lambda sid=session_id: self._navigate_back(sid)
        )
        surface.configure_standard_actions(
            on_speak=lambda sid=session_id: self._toggle_speech(sid),
            on_copy=lambda sid=session_id: self._copy(sid),
            on_paste=lambda sid=session_id: self._paste(sid),
            on_archive=lambda sid=session_id: self._archive(sid),
            on_follow_up=lambda sid=session_id: self._toggle_follow_up(sid),
        )
        surface.bind_feedback_submit(
            lambda outcome, reason, note, save_case, sid=session_id, rendered=view: (
                self._submit_feedback(
                    sid,
                    rendered.step_id,
                    outcome,
                    reason,
                    note,
                    save_case,
                )
                if rendered.step_id is not None
                else None
            )
        )
        if primary_host is not None and show_on_create:
            dialog.show()
        return view

    def _configure_voice_control(self, snapshot: SessionSnapshot, view: _SessionView) -> None:
        global_projection = getattr(self, "_voice_projection", None)
        capture_id = snapshot.voice_capture_id
        phase = snapshot.voice_capture_phase
        level = snapshot.voice_audio_level
        silence_detected = snapshot.voice_silence_detected
        if (
            capture_id is None
            and global_projection is not None
            and global_projection.workflow_id == snapshot.session_id
        ):
            capture_id = global_projection.capture_id
            phase = global_projection.capture_phase
            silence_detected = global_projection.silence_detected

        if capture_id is not None and phase is not None:
            finalizing = phase in {
                VoiceCapturePhase.STOP_REQUESTED,
                VoiceCapturePhase.FINALIZING,
                VoiceCapturePhase.CANCEL_REQUESTED,
            }
            view.surface.configure_voice_action(
                word=_voice_status_word(
                    phase,
                    silence_detected=silence_detected,
                ),
                level=level,
                listening=not finalizing,
                silence=silence_detected,
                command=(lambda cid=capture_id: self._command_sink(StopVoiceCapture(cid))) if not finalizing else None,
                enabled=not finalizing,
                tooltip=(
                    "Finalizing Voice Input"
                    if finalizing
                    else "No sound detected; click to stop Voice Input"
                    if silence_detected
                    else "Click to stop Voice Input"
                ),
                active=True,
            )
            view.surface.set_follow_up_send_enabled(False)
            return

        projection = global_projection
        capability = projection.capability if projection is not None else VoiceCapabilityPhase.SETUP_REQUIRED
        ready_status = snapshot.status in {SessionStatus.VOICE_REVIEW, SessionStatus.CONTEXT_QUESTION} or (
            snapshot.status in {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED}
            and snapshot.active_invocation_id is None
            and "follow_up" in snapshot.available_actions
        )
        enabled = capability is VoiceCapabilityPhase.READY and ready_status
        if snapshot.active_invocation_id is not None or snapshot.status in {
            SessionStatus.READING_INPUT,
            SessionStatus.PREPARING_REQUEST,
            SessionStatus.REQUESTING_PROVIDER,
            SessionStatus.PROCESSING_RESULT,
        }:
            tooltip = "Voice Input is available after the current answer finishes"
        elif capability is not VoiceCapabilityPhase.READY:
            tooltip = projection.message if projection is not None and projection.message else "Set up Voice Input from the tray"
        else:
            tooltip = "Click to start Voice Input (Ctrl+Alt+W); audio is not saved"
        view.surface.configure_voice_action(
            word=_voice_status_word(None, silence_detected=False),
            level=snapshot.voice_audio_level,
            listening=False,
            silence=False,
            command=(lambda sid=snapshot.session_id: self._start_popup_voice(sid)) if enabled else None,
            enabled=enabled,
            tooltip=tooltip,
            active=False,
        )
        view.surface.set_follow_up_send_enabled(
            snapshot.voice_capture_id is None
            and bool(view.surface.follow_entry.get().strip())
        )

    def _start_popup_voice(self, workflow_id: str) -> None:
        view = self._interactive_view(workflow_id)
        if view is None:
            return
        if view.last_snapshot is not None and view.last_snapshot.status is not SessionStatus.VOICE_REVIEW:
            self._show_follow_up(workflow_id)
        self._command_sink(StartPopupVoiceCapture(workflow_id, VoiceCaptureId(uuid.uuid4().hex)))

    def _register_view(
        self,
        session_id: str,
        view: _SessionView,
        *,
        focus_on_show: bool = True,
        announce_shown: bool = True,
    ) -> None:
        control = self._popup_control(session_id, view)
        control.observe_focus(PopupControlRegistered())
        dialog = view.dialog
        toggle_voice_draft_mode = lambda event, sid=session_id: self._popup_shortcut(
            event,
            self._toggle_voice_draft_mode,
            sid,
        )
        navigate_back = lambda event, sid=session_id: self._popup_shortcut(
            event,
            self._navigate_back,
            sid,
        )
        dialog.root.bind("<FocusOut>", lambda _event, sid=session_id: self._close_if_outside(sid), add="+")
        dialog.root.bind("<FocusIn>", lambda _event, sid=session_id: self._focus_in(sid), add="+")
        dialog.root.bind("<ButtonPress>", lambda _event, sid=session_id: self._pointer_pressed_inside(sid), add="+")
        dialog.root.bind("<Control-q>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_speech, sid), add="+")
        dialog.root.bind("<Control-e>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_pin, sid), add="+")
        dialog.root.bind("<Control-c>", lambda event, sid=session_id: self._popup_shortcut(event, self._copy, sid), add="+")
        dialog.root.bind("<Control-s>", lambda event, sid=session_id: self._popup_shortcut(event, self._archive, sid), add="+")
        dialog.root.bind("<Control-r>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_feedback, sid), add="+")
        dialog.root.bind("<Control-v>", lambda event, sid=session_id: self._paste_shortcut(event, sid), add="+")
        dialog.root.bind("<Control-z>", navigate_back, add="+")
        dialog.root.bind("<Control-Return>", toggle_voice_draft_mode, add="+")
        dialog.root.bind("<Control-KP_Enter>", toggle_voice_draft_mode, add="+")
        dialog.root.bind("<Control-slash>", lambda event, sid=session_id: self._popup_shortcut(event, self._toggle_follow_up, sid), add="+")
        view.surface.bind_header_double_click(lambda _event, sid=session_id: self._header_double_click(sid))
        view.surface.bind_back_shortcut(navigate_back)
        view.surface.bind_voice_draft_mode_toggle(toggle_voice_draft_mode)
        view.surface.bind_voice_draft_paste(
            lambda event, sid=session_id: self._paste_shortcut(event, sid)
        )
        if announce_shown:
            control.observe_focus(PopupControlShown())
            if focus_on_show:
                self._schedule_initial_focus(session_id, view)

    def _schedule_initial_focus(self, session_id: str, view: _SessionView) -> None:
        def establish_initial_focus() -> None:
            control = self._popup_control(session_id, view)
            if self._views.get(session_id) is not view or control.focused_inside:
                return
            view.surface.focus_content()
            control.observe_focus(ToolkitFocusEntered())

        view.dialog.lifecycle.schedule(0, establish_initial_focus)

    def _shortcut(self, action: Callable[[str], None], session_id: str) -> str | None:
        view = self._interactive_view(session_id)
        if view is not None and self._popup_control(session_id, view).focused_inside:
            action(session_id)
        return "break" if view is not None else None

    def _popup_shortcut(self, event, action: Callable[[str], None], session_id: str) -> str:
        if _has_only_popup_shortcut_modifiers(event):
            return self._shortcut(action, session_id)
        return "break"

    def _paste_shortcut(self, event, session_id: str) -> str | None:
        if not _has_only_popup_shortcut_modifiers(event):
            return "break"
        view = self._views.get(session_id)
        if view is not None and view.last_snapshot is not None and view.last_snapshot.status is SessionStatus.VOICE_REVIEW:
            return self._shortcut(self._paste, session_id)
        if _accepts_native_paste(getattr(event, "widget", None)):
            return None
        return self._shortcut(self._paste, session_id)

    def _toggle_voice_draft_mode(self, session_id: str) -> None:
        view = self._views.get(session_id)
        if view is None or view.last_snapshot is None or view.last_snapshot.status is not SessionStatus.VOICE_REVIEW:
            return
        view.voice_draft_editing = not view.voice_draft_editing
        view.surface.set_voice_draft_editing(view.voice_draft_editing)
        self._project_popup_context(session_id, view)

    def _navigate_back(self, session_id: str) -> None:
        self._command_sink(NavigateWorkflowBack(session_id))

    def _header_double_click(self, session_id: str) -> str:
        self._toggle_pin(session_id)
        return "break"

    def _focus_in(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        self._popup_control(session_id, view).observe_focus(ToolkitFocusEntered())

    def _pointer_pressed_inside(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        self._popup_control(session_id, view).observe_focus(PopupInsidePointerPressed())

    def _close_if_outside(self, session_id: str) -> None:
        view = self._interactive_view(session_id)
        if view is None:
            return
        self._popup_control(session_id, view).observe_focus(PopupOutsideFocusRequested())


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
        visual_state=(
            previous.speaking,
            previous.voice_capture_id,
            previous.voice_capture_phase,
            previous.voice_audio_level,
            previous.voice_silence_detected,
            previous.voice_status_text,
            previous.voice_follow_up_insertion,
        ) != (
            current.speaking,
            current.voice_capture_id,
            current.voice_capture_phase,
            current.voice_audio_level,
            current.voice_silence_detected,
            current.voice_status_text,
            current.voice_follow_up_insertion,
        ),
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
