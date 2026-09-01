from __future__ import annotations

import queue
import inspect
from dataclasses import replace

from ClipAI.core.commands import ActivateWorkflow, ArchiveResult, CloseSession, ControlSurfaceActivated, ControlSurfaceReleased, CopyResult, FollowUp, NavigateWorkflowBack, PasteResult, StartPopupVoiceCapture, StopVoiceCapture, SubmitActionFeedback, SubmitContextualQuestion, TogglePin, ToggleSpeech, WorkflowAttentionCompleted
from ClipAI.core.models import ActionFeedbackContract, ControlSurfaceRef, FeedbackReason, OutputOperationResult, PasteTarget, PopupBounds, WorkflowAttention
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceCaptureId, VoiceCapturePhase, VoiceCaptureSurfaceContext, VoiceDraftInsertion, VoiceFollowUpInsertion, VoiceLanguage, VoiceOrigin, VoiceProjection
from ClipAI.ui.base_dialog import BaseResultSurface, _VoiceWaveIndicator
from ClipAI.ui.popup_control import PopupControlRegistered, PopupControlShown, PopupOwnedDialogOpened, ToolkitFocusEntered
from ClipAI.ui.result_dialog import LatestSnapshotMailbox, ResultDialogPresenter, _SessionView, _content_render_key, _voice_status_word, workflow_render_patch


def test_voice_waveform_uses_canvas_and_packs_after_right_anchors() -> None:
    source = inspect.getsource(BaseResultSurface._build)
    creation = source.index("self.voice_input_button = _VoiceWaveIndicator")
    overflow = source.index("self._overflow_button = self.add_action_slot", creation)
    waveform = source.index('self.voice_input_button.pack(side="left"', overflow)

    assert creation < overflow < waveform
    assert 'self._action_tooltips["voice_input"] = _Tooltip' in source
    assert "self.action_status_label = ctk.CTkLabel(\n            self.actions" in source
    assert "width=68" in source


def test_voice_waveform_animation_uses_only_the_dialog_lifecycle() -> None:
    source = inspect.getsource(_VoiceWaveIndicator)

    assert "self.after(" not in source
    assert "self.after_cancel(" not in source
    assert "self._lifecycle.schedule(" in source
    assert "self._lifecycle.cancel(" in source
    assert "if self._lifecycle.is_closed:" in source


def test_voice_waveform_silence_forces_the_target_to_a_flat_line() -> None:
    class Indicator:
        def configure(self, **kwargs) -> None:
            self.configured = kwargs

        def _render(self) -> None:
            self.rendered = True

        def _ensure_animation(self) -> None:
            self.animation_checked = True

    indicator = Indicator()

    _VoiceWaveIndicator.update_state(
        indicator,
        word="無聲",
        level=0.9,
        listening=True,
        silence=True,
        enabled=True,
        active=True,
        command=lambda: None,
    )

    assert indicator._target_amplitude == 0.0
    assert indicator._silence is True
    assert indicator._word == "無聲"
    assert indicator.rendered is True
    assert indicator.animation_checked is True


def test_voice_waveform_tick_eases_toward_the_authoritative_level() -> None:
    class Lifecycle:
        is_closed = False

    class Indicator:
        AMPLITUDE_EASING = _VoiceWaveIndicator.AMPLITUDE_EASING

        def _render(self) -> None:
            self.rendered = True

        def _ensure_animation(self) -> None:
            self.animation_checked = True

    indicator = Indicator()
    indicator._job = "scheduled"
    indicator._lifecycle = Lifecycle()
    indicator._target_amplitude = 1.0
    indicator._amplitude = 0.0
    indicator._listening = True
    indicator._phase = 0.0

    _VoiceWaveIndicator._tick(indicator)

    assert indicator._amplitude == _VoiceWaveIndicator.AMPLITUDE_EASING
    assert indicator._amplitude != indicator._target_amplitude
    assert indicator._phase > 0.0
    assert indicator.rendered is True
    assert indicator.animation_checked is True


def test_voice_waveform_colors_distinguish_disabled_silence_active_and_default() -> None:
    indicator = type("Indicator", (), {
        "_DISABLED_PILL": _VoiceWaveIndicator._DISABLED_PILL,
        "_ACTIVE_PILL": _VoiceWaveIndicator._ACTIVE_PILL,
        "_DEFAULT_PILL": _VoiceWaveIndicator._DEFAULT_PILL,
        "_DISABLED_LINE": _VoiceWaveIndicator._DISABLED_LINE,
        "_SILENCE_LINE": _VoiceWaveIndicator._SILENCE_LINE,
        "_ACTIVE_LINE": _VoiceWaveIndicator._ACTIVE_LINE,
        "_DEFAULT_LINE": _VoiceWaveIndicator._DEFAULT_LINE,
    })()

    indicator._enabled = False
    indicator._active = True
    indicator._silence = True
    disabled = _VoiceWaveIndicator._colors(indicator)
    indicator._enabled = True
    silence = _VoiceWaveIndicator._colors(indicator)
    indicator._silence = False
    active = _VoiceWaveIndicator._colors(indicator)
    indicator._active = False
    default = _VoiceWaveIndicator._colors(indicator)

    assert disabled[:2] == (
        _VoiceWaveIndicator._DISABLED_PILL,
        _VoiceWaveIndicator._DISABLED_LINE,
    )
    assert silence[:2] == (
        _VoiceWaveIndicator._ACTIVE_PILL,
        _VoiceWaveIndicator._SILENCE_LINE,
    )
    assert active[:2] == (
        _VoiceWaveIndicator._ACTIVE_PILL,
        _VoiceWaveIndicator._ACTIVE_LINE,
    )
    assert default[:2] == (
        _VoiceWaveIndicator._DEFAULT_PILL,
        _VoiceWaveIndicator._DEFAULT_LINE,
    )


def test_voice_waveform_font_uses_scaled_negative_pixel_size_and_is_cached(monkeypatch) -> None:
    created: list[dict[str, object]] = []
    font = object()
    monkeypatch.setattr(
        "ClipAI.ui.base_dialog.tkfont.Font",
        lambda **kwargs: created.append(kwargs) or font,
    )
    indicator = type("Indicator", (), {
        "FONT_BASE_PX": 10,
        "_font_family": "Test UI",
        "_font": None,
        "_font_px": None,
    })()

    assert _VoiceWaveIndicator._scaled_font(indicator, 1.5) is font
    assert _VoiceWaveIndicator._scaled_font(indicator, 1.5) is font

    assert len(created) == 1
    assert created[0]["root"] is indicator
    assert created[0]["size"] == -15


def test_voice_waveform_line_ends_before_the_measured_status_word() -> None:
    class Font:
        def measure(self, word: str) -> int:
            assert word == "聆聽"
            return 30

    class Indicator:
        BASE_WIDTH = 82
        BASE_HEIGHT = 22

        def _widget_scaling(self) -> float:
            return 1.5

        def _scaled_font(self, _scaling: float) -> Font:
            return Font()

        def _colors(self):
            return "pill", "line", "word"

        def configure(self, **kwargs) -> None:
            self.configured = kwargs

        def delete(self, _tag: str) -> None:
            pass

        def _draw_rounded_pill(self, *_args) -> None:
            pass

        def create_text(self, *_args, **_kwargs) -> None:
            pass

        def create_line(self, *points, **_kwargs) -> None:
            self.points = points

    indicator = Indicator()
    indicator._word = "聆聽"
    indicator._amplitude = 0.7
    indicator._phase = 0.0

    _VoiceWaveIndicator._render(indicator)

    width = round(82 * 1.5)
    padding = 7.0 * 1.5
    measured_line_right = width - padding - 30 - padding
    x_coordinates = indicator.points[0::2]
    assert max(x_coordinates) <= measured_line_right


class Root:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def withdraw(self) -> None:
        self.events.append("withdraw")

    def deiconify(self) -> None:
        self.events.append("deiconify")

    def focus_get(self):
        return self

    def winfo_toplevel(self):
        return self


class Dialog:
    def __init__(self, events: list[str], *, alive: bool = True) -> None:
        self.root = Root(events)
        self.lifecycle = type("Lifecycle", (), {
            "focus": lambda _self: events.append("focus") or True,
        })()
        self.alive = alive
        self.pinned = False
        self.native_foreground = True

    def is_alive(self) -> bool:
        return self.alive

    def is_visible(self) -> bool:
        return self.alive

    def close(self) -> None:
        self.alive = False
        self.root.events.append("close")

    def apply_external_output_visibility(self, visibility: str) -> None:
        self.root.events.append(f"visibility:{visibility}")

    def contains_screen_point(self, x: int, y: int) -> bool:
        return (x, y) == (10, 10)

    def native_owns_foreground(self) -> bool:
        return self.native_foreground


class FollowUpEntry:
    def __init__(self) -> None:
        self.text = ""
        self.bindings = {}

    def get(self) -> str:
        return self.text

    def delete(self, _start, _end) -> None:
        self.text = ""

    def bind(self, event, callback, **_kwargs) -> None:
        self.bindings[event] = callback


class Surface:
    def __init__(self, selected: str | None, events: list[str]) -> None:
        self.selected = selected
        self.events = events
        self.overflow_expanded = False
        self.feedback_available = False
        self.header_double_click_callback = None
        self.voice_draft_paste_callback = None
        self.focus_result = True
        self.follow_up_visible = False
        self.follow_entry = FollowUpEntry()
        self.follow_send_button = type("Button", (), {
            "command": None,
            "configure": lambda button, **kwargs: setattr(
                button,
                "command",
                kwargs.get("command", button.command),
            ),
        })()

    def selected_text(self) -> str | None:
        return self.selected

    def set_content_chunks(self, chunks) -> None:
        self.events.append(("content", chunks))

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None:
        self.events.append(f"{slot_id}:{enabled}")

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:pulse:{duration_ms}")

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:error:{duration_ms}")

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None:
        self.events.append(f"message:{text}:{duration_ms}")

    def set_speaker_active(self, active: bool) -> None:
        self.events.append(f"speaker:{active}")

    def toggle_pin(self) -> bool:
        self.events.append("pin:toggled")
        return True

    def bind_header_double_click(self, callback) -> None:
        self.header_double_click_callback = callback

    def bind_back_shortcut(self, callback) -> None:
        self.back_shortcut_callback = callback

    def bind_voice_draft_mode_toggle(self, callback) -> None:
        self.voice_draft_mode_toggle_callback = callback

    def bind_voice_draft_paste(self, callback) -> None:
        self.voice_draft_paste_callback = callback

    def focus_content(self) -> bool:
        return self.focus_result

    def configure_action_contract(self, contract, input_source: str) -> None:
        self.events.append(("contract", contract, input_source))

    def show_action_guidance_hint(self) -> None:
        self.events.append("guidance:shown")

    def configure_feedback(self, contract, state, message, on_submit) -> None:
        self.feedback_submit = on_submit
        self.events.append(("feedback", state, message))

    def hide_feedback(self) -> None:
        self.events.append("feedback:hidden")

    def toggle_feedback_overlay(self) -> bool:
        self.events.append("feedback:toggled")
        return self.feedback_available

    def close_feedback_overlay(self) -> None:
        self.events.append("feedback:closed")

    def collapse_overflow(self) -> None:
        self.events.append("overflow:collapsed")

    def set_paste_focus_state(self, focused, target, *, voice_draft_editing=None) -> None:
        self.focused = focused
        self.paste_target = target
        self.voice_draft_editing = voice_draft_editing
        if voice_draft_editing is not None:
            self.events.append(f"voice-mode:{voice_draft_editing}")

    def set_voice_draft_editing(self, editing: bool) -> None:
        self.voice_draft_editing = editing
        self.events.append(f"voice-editor:{editing}")

    def set_editable_content(self, text: str, _on_changed, *, caret_offset=None) -> None:
        self.events.append(f"voice-content:{text}")
        if caret_offset is not None:
            self.events.append(f"voice-caret:{caret_offset}")

    def configure_voice_action(self, **kwargs) -> None:
        self.voice_action = kwargs
        self.events.append(("voice-action", kwargs))

    def insert_follow_up_text(self, text: str) -> None:
        self.events.append(f"follow-up-insert:{text}")

    def set_follow_up_send_enabled(self, enabled: bool) -> None:
        self.events.append(f"follow-up-send:{enabled}")

    def show_follow_up(self, initial_text: str = "") -> None:
        self.follow_up_visible = True
        self.events.append(f"follow-up-show:{initial_text}")

    def hide_follow_up(self) -> None:
        self.follow_up_visible = False
        self.events.append("follow-up-hide")

    def clear_follow_up_text(self) -> None:
        self.follow_entry.delete(0, "end")
        self.events.append("follow-up-cleared")

    def set_follow_up_active(self, active: bool) -> None:
        self.events.append(f"follow-up-active:{active}")


def presenter_with_selection(selected: str | None):
    events: list[str] = []
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._views = {"s1": _SessionView(Dialog(events), Surface(selected, events))}
    presenter._command_sink = lambda command: events.append(command)
    presenter._paste_target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    presenter._paste_target_updates = queue.Queue()
    presenter._shortcut_guide_focus_hold_active = False
    presenter._shortcut_guide_focus_return = None
    presenter._focus_transition_diagnostics = False
    presenter._voice_projection = VoiceProjection(
        VoiceCapabilityPhase.READY,
        VoiceLanguage("zh-TW"),
    )
    control = presenter._popup_control("s1", presenter._views["s1"])
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    control.observe_focus(ToolkitFocusEntered())
    events.clear()
    return presenter, events


def test_text_command_carries_popup_selection() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._send_text_command("s1", CopyResult)
    assert events == [CopyResult("s1", "selected")]


def test_copy_and_archive_wait_for_typed_acknowledgment() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._copy("s1")
    presenter._archive("s1")
    assert len(events) == 2
    assert isinstance(events[0], CopyResult) and events[0].text == "selected" and events[0].operation_id
    assert isinstance(events[1], ArchiveResult) and events[1].text == "selected" and events[1].operation_id


def test_acknowledgment_projects_success_and_ignores_stale_operation() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._archive("s1")
    operation_id = events[-1].operation_id
    events.clear()
    presenter._apply_output_operation(OutputOperationResult("old", "s1", "archive", "succeeded"))
    assert events == []
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "archive", "succeeded"))
    assert "archive:pulse:1000" in events


def test_late_output_operation_closes_workflow_for_dead_view() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].dialog.alive = False

    presenter._apply_output_operation(OutputOperationResult("late", "s1", "archive", "pending"))

    assert events == [CloseSession("s1")]
    assert presenter._views == {}


def test_late_completed_snapshot_closes_workflow_for_dead_view() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].dialog.alive = False
    snapshot = SessionSnapshot("s1", 1, SessionStatus.COMPLETED, "a", "A", "model", content="late")

    presenter._apply(snapshot)

    assert events == [CloseSession("s1")]
    assert presenter._views == {}


def test_closed_snapshot_cleanup_is_idempotent() -> None:
    presenter, events = presenter_with_selection("selected")
    snapshot = SessionSnapshot("s1", 1, SessionStatus.CLOSED, "a", "A", "model")

    presenter._apply(snapshot)
    presenter._apply(snapshot)

    assert events == ["close"]
    assert presenter._views == {}


def test_stopped_snapshot_has_distinct_content_render_key() -> None:
    snapshot = SessionSnapshot("s1", 1, SessionStatus.STOPPED, "a", "A", "model", status_text="Stopped")

    assert _content_render_key(snapshot) == (SessionStatus.STOPPED, "", "Stopped", None)


def test_latest_snapshot_mailbox_coalesces_each_workflow_to_highest_revision() -> None:
    mailbox = LatestSnapshotMailbox()
    mailbox.put(SessionSnapshot("one", 1, SessionStatus.REQUESTING_PROVIDER, "a", "A", "m"))
    mailbox.put(SessionSnapshot("one", 3, SessionStatus.COMPLETED, "a", "A", "m", content="done"))
    mailbox.put(SessionSnapshot("one", 2, SessionStatus.REQUESTING_PROVIDER, "a", "A", "m", content="late partial"))
    mailbox.put(SessionSnapshot("two", 1, SessionStatus.FAILED, "a", "A", "m", error="failed"))

    drained = {snapshot.session_id: snapshot for snapshot in mailbox.drain()}
    assert drained["one"].revision == 3
    assert drained["one"].status == SessionStatus.COMPLETED
    assert drained["two"].status == SessionStatus.FAILED
    assert mailbox.drain() == ()


def test_voice_status_word_keeps_phase_semantics_in_the_presenter() -> None:
    assert _voice_status_word(None, silence_detected=False) == "語音"
    assert _voice_status_word(VoiceCapturePhase.LISTENING, silence_detected=False) == "聆聽"
    assert _voice_status_word(VoiceCapturePhase.LISTENING, silence_detected=True) == "無聲"
    for phase in (
        VoiceCapturePhase.STOP_REQUESTED,
        VoiceCapturePhase.FINALIZING,
        VoiceCapturePhase.CANCEL_REQUESTED,
    ):
        assert _voice_status_word(phase, silence_detected=True) == "整理"


def test_completed_popup_offers_voice_follow_up_and_emits_typed_start() -> None:
    presenter, events = presenter_with_selection(None)
    snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        available_actions=("follow_up",),
    )

    presenter._configure_voice_control(snapshot, presenter._views["s1"])
    action = presenter._views["s1"].surface.voice_action

    assert action["enabled"] is True
    assert action["active"] is False
    assert action["word"] == "語音"
    assert action["level"] == 0.0
    assert action["listening"] is False
    assert action["silence"] is False
    action["command"]()
    assert isinstance(events[-1], StartPopupVoiceCapture)
    assert events[-1].workflow_id == "s1"
    assert isinstance(events[-1].capture_id, VoiceCaptureId)


def test_contextual_question_opens_standard_composer_and_emits_initial_submit() -> None:
    presenter, events = presenter_with_selection(None)
    snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.CONTEXT_QUESTION,
        "contextual_question",
        "問這段",
        "m",
        source_preview="Selection: fixed source",
        available_actions=("follow_up",),
        contextual_source_text="fixed source",
        contextual_source_kind="selection",
        question_composer_revision=1,
    )
    view = presenter._views["s1"]
    view.last_snapshot = replace(snapshot, revision=0, question_composer_revision=0)
    view.revision = 0

    presenter._apply(snapshot)
    view.surface.follow_entry.text = "這句話代表什麼？"
    view.surface.follow_entry.bindings["<KeyRelease>"](None)
    view.surface.follow_send_button.command()

    assert "follow-up-show:" in events
    assert "follow-up-send:False" in events
    assert "follow-up-send:True" in events
    assert events[-1] == SubmitContextualQuestion("s1", "這句話代表什麼？")


def test_active_voice_follow_up_uses_same_control_to_stop() -> None:
    presenter, events = presenter_with_selection(None)
    capture_id = VoiceCaptureId("capture-1")
    snapshot = SessionSnapshot(
        "s1",
        2,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        available_actions=("follow_up",),
        voice_capture_id=capture_id,
        voice_capture_phase=VoiceCapturePhase.LISTENING,
        voice_audio_level=0.8,
    )

    presenter._configure_voice_control(snapshot, presenter._views["s1"])
    action = presenter._views["s1"].surface.voice_action

    assert action["active"] is True
    assert action["word"] == "聆聽"
    assert action["level"] == 0.8
    assert action["listening"] is True
    assert action["silence"] is False
    assert "follow-up-send:False" in events
    action["command"]()
    assert events[-1] == StopVoiceCapture(capture_id)


def test_voice_silence_projects_real_level_but_marks_the_widget_silent() -> None:
    presenter, _events = presenter_with_selection(None)
    snapshot = SessionSnapshot(
        "s1",
        2,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        available_actions=("follow_up",),
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.LISTENING,
        voice_audio_level=0.8,
        voice_silence_detected=True,
    )

    presenter._configure_voice_control(snapshot, presenter._views["s1"])
    action = presenter._views["s1"].surface.voice_action

    assert action["word"] == "無聲"
    assert action["level"] == 0.8
    assert action["listening"] is True
    assert action["silence"] is True


def test_every_finalizing_phase_disables_the_control_and_overrides_silence() -> None:
    presenter, _events = presenter_with_selection(None)
    for revision, phase in enumerate(
        (
            VoiceCapturePhase.STOP_REQUESTED,
            VoiceCapturePhase.FINALIZING,
            VoiceCapturePhase.CANCEL_REQUESTED,
        ),
        start=2,
    ):
        snapshot = SessionSnapshot(
            "s1",
            revision,
            SessionStatus.COMPLETED,
            "a",
            "A",
            "m",
            available_actions=("follow_up",),
            voice_capture_id=VoiceCaptureId("capture-1"),
            voice_capture_phase=phase,
            voice_audio_level=0.7,
            voice_silence_detected=True,
        )

        presenter._configure_voice_control(snapshot, presenter._views["s1"])
        action = presenter._views["s1"].surface.voice_action

        assert action["word"] == "整理"
        assert action["level"] == 0.7
        assert action["listening"] is False
        assert action["silence"] is True
        assert action["enabled"] is False
        assert action["active"] is True
        assert action["command"] is None


def test_global_voice_projection_does_not_replace_snapshot_audio_level() -> None:
    presenter, _events = presenter_with_selection(None)
    presenter._voice_projection = VoiceProjection(
        VoiceCapabilityPhase.READY,
        VoiceLanguage("zh-TW"),
        capture_id=VoiceCaptureId("capture-1"),
        capture_phase=VoiceCapturePhase.LISTENING,
        workflow_id="s1",
        audio_level=0.95,
    )
    snapshot = SessionSnapshot(
        "s1",
        2,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        available_actions=("follow_up",),
        voice_audio_level=0.25,
    )

    presenter._configure_voice_control(snapshot, presenter._views["s1"])

    assert presenter._views["s1"].surface.voice_action["level"] == 0.25


def test_shortcut_started_voice_follow_up_immediately_opens_the_review_field() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        content="answer",
        available_actions=("follow_up",),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.content = previous.content
    view.flashed_completion_keys.add(previous.content)

    presenter._apply(previous.evolve(
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.STARTING,
    ))

    assert view.surface.follow_up_visible is True
    assert "follow-up-show:" in events
    assert "follow-up-active:True" in events


def test_shortcut_started_voice_follow_up_can_submit_its_reviewed_text() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        content="answer",
        available_actions=("follow_up",),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.content = previous.content
    view.flashed_completion_keys.add(previous.content)

    presenter._apply(previous.evolve(
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.STARTING,
    ))
    view.last_snapshot = previous.evolve()
    view.surface.follow_entry.get = lambda: "What changed?"

    assert view.surface.follow_send_button.command is not None
    view.surface.follow_send_button.command()

    assert events[-1] == FollowUp("s1", "What changed?")


def test_shortcut_started_voice_follow_up_can_submit_with_enter() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        content="answer",
        available_actions=("follow_up",),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.content = previous.content
    view.flashed_completion_keys.add(previous.content)

    presenter._apply(previous.evolve(
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.STARTING,
    ))
    view.last_snapshot = previous.evolve()
    view.surface.follow_entry.get = lambda: "What changed?"

    view.surface.follow_entry.bindings["<Return>"](None)

    assert events[-1] == FollowUp("s1", "What changed?")


def test_sent_follow_up_clears_the_next_question_input() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        available_actions=("follow_up",),
    )

    presenter._show_follow_up("s1")
    view.surface.follow_entry.text = "First question"
    view.surface.follow_send_button.command()
    presenter._show_follow_up("s1")

    assert "follow-up-active:True" in events
    assert events[-1] == "follow-up-send:False"
    assert view.surface.follow_entry.text == ""


def test_provider_activity_disables_popup_voice_input() -> None:
    presenter, _events = presenter_with_selection(None)
    snapshot = SessionSnapshot(
        "s1",
        2,
        SessionStatus.REQUESTING_PROVIDER,
        "a",
        "A",
        "m",
        active_invocation_id="invocation-1",
    )

    presenter._configure_voice_control(snapshot, presenter._views["s1"])
    action = presenter._views["s1"].surface.voice_action

    assert action["enabled"] is False
    assert "answer finishes" in action["tooltip"]


def test_follow_up_voice_insertion_is_applied_once_at_the_live_caret() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        content="answer",
        available_actions=("follow_up",),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.content = previous.content
    view.flashed_completion_keys.add(previous.content)
    insertion = VoiceFollowUpInsertion(VoiceCaptureId("capture-1"), "追加問題")

    presenter._apply(previous.evolve(voice_follow_up_insertion=insertion))
    presenter._apply(replace(previous, revision=3, voice_follow_up_insertion=insertion))

    assert events.count("follow-up-insert:追加問題") == 1


def test_follow_up_cannot_hide_or_submit_while_voice_capture_is_active() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.COMPLETED,
        "a",
        "A",
        "m",
        voice_capture_id=VoiceCaptureId("capture-1"),
        voice_capture_phase=VoiceCapturePhase.LISTENING,
    )
    view.surface.follow_up_visible = True

    presenter._toggle_follow_up("s1")

    assert view.surface.follow_up_visible is True
    assert "message:請先停止語音輸入:1500" in events


def test_speaking_and_pin_updates_do_not_patch_unchanged_content() -> None:
    initial = SessionSnapshot("one", 1, SessionStatus.COMPLETED, "a", "A", "m", content="result")
    speaking = replace(initial, revision=2, speaking=True)
    pinned = replace(speaking, revision=3, pinned=True)

    speaking_patch = workflow_render_patch(initial, speaking)
    pinned_patch = workflow_render_patch(speaking, pinned)

    assert speaking_patch.content is False
    assert speaking_patch.visual_state is True
    assert pinned_patch.content is False
    assert pinned_patch.header is True


def test_speaker_command_waits_for_snapshot_to_change_icon() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    assert len(events) == 1
    assert isinstance(events[0], ToggleSpeech) and events[0].text == "selected" and events[0].operation_id


def test_speech_operation_projects_to_speaker_slot() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "speech", "pending"))
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "speech", "succeeded"))
    assert "speaker:pulse:1000" in events


def test_speech_failure_projects_to_speaker_slot() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "speech", "pending"))
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "speech", "failed"))
    assert "speaker:error:1000" in events


def test_paste_emits_identified_command_and_waits_for_pending_projection() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._paste("s1")
    assert len(events) == 2
    assert events[0] == "visibility:hidden"
    assert isinstance(events[1], PasteResult) and events[1].text == "selected" and events[1].operation_id


def test_pinned_unconfirmed_paste_restores_without_activation() -> None:
    presenter, events = presenter_with_selection("selected")
    view = presenter._views["s1"]
    view.dialog.pinned = True

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "dispatched_unconfirmed",
    ))

    assert "visibility:visible_no_activate" in events
    assert view.surface.focused is False


def test_unpinned_paste_failure_restores_with_focus() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "failed"))

    assert "visibility:visible_activate" in events


def test_cancelled_paste_restores_without_stealing_focus() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "cancelled"))

    assert "visibility:visible_no_activate" in events
    assert "visibility:visible_activate" not in events
    assert "message:已取消貼上:1500" in events


def test_cleanup_failed_paste_restores_without_stealing_focus() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "cleanup_failed",
        message="Clipboard restore failed.",
    ))

    assert "visibility:visible_no_activate" in events
    assert "visibility:visible_activate" not in events
    assert "message:Clipboard restore failed.:3000" in events


def test_unpinned_unconfirmed_paste_stays_hidden_without_stealing_focus() -> None:
    presenter, events = presenter_with_selection("selected")
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "dispatched_unconfirmed",
        message="Paste was sent; confirm before trying again.",
    ))

    assert "visibility:visible_activate" not in events
    assert "visibility:visible_no_activate" not in events
    assert presenter._views["s1"] is view
    assert "message:Paste was sent; confirm before trying again.:2500" in events


def test_voice_attention_after_paste_terminal_reveals_the_existing_popup() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))

    presenter._apply_attention(WorkflowAttention(
        "attention-1",
        "s1",
        "Preparing microphone",
        duration_ms=1500,
        warning=False,
    ))
    assert "visibility:visible_activate" not in events

    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "dispatched_unconfirmed",
    ))

    assert "visibility:visible_activate" in events
    assert "focus" in events
    assert WorkflowAttentionCompleted("attention-1", "s1", True) in events


def test_stale_paste_result_does_not_restore_current_transition() -> None:
    presenter, events = presenter_with_selection("selected")
    view = presenter._views["s1"]
    presenter._paste("s1")

    presenter._apply_output_operation(OutputOperationResult("old", "s1", "paste", "cancelled"))

    assert "visibility:visible_activate" not in events
    assert "visibility:visible_no_activate" not in events


def test_pin_updates_visual_state_before_emitting_command() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._toggle_pin("s1")
    assert events == ["pin:toggled", TogglePin("s1")]


def test_feedback_submission_is_a_typed_identified_command() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._submit_feedback("s1", "step-1", "needs_adjustment", "meaning_lost", "Too aggressive", True)

    assert len(events) == 1
    command = events[0]
    assert isinstance(command, SubmitActionFeedback)
    assert command.session_id == "s1"
    assert command.step_id == "step-1"
    assert command.operation_id
    assert command.reason == "meaning_lost"
    assert command.save_case is True


def test_ctrl_r_feedback_request_reports_unsupported_recipe() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._toggle_feedback("s1")

    assert events == ["feedback:toggled", "message:此 Recipe 尚未啟用回饋:1000"]


def test_ctrl_r_feedback_request_opens_supported_recipe_overlay() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._views["s1"].surface.feedback_available = True

    presenter._toggle_feedback("s1")

    assert events == ["feedback:toggled"]


def test_ctrl_slash_toggles_follow_up_for_active_popup() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    presenter._toggle_follow_up = lambda session_id: events.append(f"follow-up:{session_id}")

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-slash>"](None)

    assert result == "break"
    assert events == ["follow-up:s1"]


def test_ctrl_z_navigates_back_for_active_popup_with_history() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    view.last_snapshot = SessionSnapshot(
        "s1", 1, SessionStatus.COMPLETED, "rewrite", "Rewrite", "Completed",
        can_navigate_back=True,
    )

    presenter._register_view("s1", view)

    class CtrlZEvent:
        state = 0x0004

    result = view.surface.back_shortcut_callback(CtrlZEvent())

    assert result == "break"
    assert events == [NavigateWorkflowBack("s1")]


def test_failed_initial_focus_attempt_does_not_claim_popup_focus() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def __init__(self) -> None:
            self.callbacks = []

        def schedule(self, _delay_ms, callback) -> str:
            self.callbacks.append(callback)
            return "scheduled"

        def focus(self) -> bool:
            return False

    presenter, _events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.popup_control = None
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    view.surface.focus_result = False
    view.dialog.native_foreground = False

    presenter._register_view("s1", view)
    view.dialog.lifecycle.callbacks[0]()

    assert presenter._popup_control("s1", view).focused_inside is False


def test_clicking_toolkit_focused_popup_requests_native_focus_and_confirms_it() -> None:
    class FocusRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

        def focus_get(self):
            return self

        def winfo_toplevel(self):
            return self

    class Lifecycle:
        def __init__(self, dialog, events) -> None:
            self.dialog = dialog
            self.events = events
            self.callbacks = []

        def focus(self) -> bool:
            self.events.append("native-focus-requested")
            self.dialog.native_foreground = True
            return True

        def schedule(self, delay_ms, callback) -> str:
            self.callbacks.append((delay_ms, callback))
            return f"scheduled-{len(self.callbacks)}"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.popup_control = None
    view.dialog.root = FocusRoot()
    view.dialog.native_foreground = False
    view.dialog.lifecycle = Lifecycle(view.dialog, events)

    presenter._register_view("s1", view, focus_on_show=False)
    view.dialog.root.bindings["<FocusIn>"](None)
    assert view.surface.focused is False

    view.dialog.root.bindings["<ButtonPress>"](None)

    assert "native-focus-requested" in events
    assert [delay_ms for delay_ms, _callback in view.dialog.lifecycle.callbacks] == [25, 25]
    for _delay_ms, callback in tuple(view.dialog.lifecycle.callbacks):
        callback()
    assert view.surface.focused is True
    assert events.count(ControlSurfaceActivated(ControlSurfaceRef("s1", "workflow"))) == 1
    assert ActivateWorkflow("s1") in events


def test_confirmed_focus_reports_control_surface_and_workflow_activation_once() -> None:
    class FocusedRoot:
        def focus_get(self):
            return self

        def winfo_toplevel(self):
            return self

    presenter, events = presenter_with_selection(None)
    presenter._views["s1"].dialog.root = FocusedRoot()

    presenter._focus_in("s1")

    assert events.count(ControlSurfaceActivated(ControlSurfaceRef("s1", "workflow"))) == 1
    assert events.count(ActivateWorkflow("s1")) == 1


def test_inside_pointer_requests_workflow_activation_before_focus_is_confirmed() -> None:
    class Lifecycle:
        def __init__(self) -> None:
            self.callbacks = []

        def focus(self) -> bool:
            return True

        def schedule(self, delay_ms, callback) -> str:
            self.callbacks.append((delay_ms, callback))
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.popup_control = None
    control = presenter._popup_control("s1", view)
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())
    view.dialog.lifecycle = Lifecycle()

    presenter._pointer_pressed_inside("s1")

    assert events == [ActivateWorkflow("s1")]
    assert [delay_ms for delay_ms, _callback in view.dialog.lifecycle.callbacks] == [25]


def test_first_outside_pointer_press_closes_popup_when_native_focus_failed() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.popup_control = None
    control = presenter._popup_control("s1", view)
    control.observe_focus(PopupControlRegistered())
    control.observe_focus(PopupControlShown())

    presenter._handle_pointer_press(100, 100)

    assert ControlSurfaceReleased(ControlSurfaceRef("s1", "workflow")) in events
    assert CloseSession("s1") in events


def test_pointer_press_inside_popup_does_not_close_it() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._handle_pointer_press(10, 10)

    assert not any(isinstance(event, CloseSession) for event in events)


def test_outside_pointer_press_closes_the_unified_entry_panel() -> None:
    class EntryPanel:
        def __init__(self) -> None:
            self.close_requests = 0

        def contains_screen_point(self, _x: int, _y: int) -> bool:
            return False

        def request_close(self) -> None:
            self.close_requests += 1

    presenter, _events = presenter_with_selection(None)
    panel = EntryPanel()
    presenter._entry_panel_dialog = panel

    presenter._handle_pointer_press(100, 100)

    assert panel.close_requests == 1


def test_presenter_commits_reused_popup_handoff_after_render() -> None:
    class EntryPanel:
        def presents(self, panel_id: str) -> bool:
            return panel_id == "panel-1"

        def close(self) -> None:
            events.append("panel:closed")

    presenter, events = presenter_with_selection(None)
    presenter._entry_panel_dialog = EntryPanel()
    presenter.transition_entry_panel_to_popup("panel-1", "s1")
    previous = SessionSnapshot(
        "s1",
        0,
        SessionStatus.REQUESTING_PROVIDER,
        "action",
        "Action",
        "model",
        status_text="Loading",
    )
    presenter._views["s1"].revision = previous.revision
    presenter._views["s1"].last_snapshot = previous

    presenter._apply(replace(previous, revision=1))

    assert "panel:closed" in events


def test_dead_popup_emits_close_intent_before_view_is_evicted() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._views["s1"].dialog.alive = False

    presenter._handle_pointer_press(100, 100)

    assert events == [CloseSession("s1")]
    assert presenter._views == {}


def test_ui_tick_closes_dead_popup_without_waiting_for_another_ui_event() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._views["s1"].dialog.alive = False
    presenter._pointer_press_reader = None
    presenter._output_updates = queue.Queue()
    presenter._updates = LatestSnapshotMailbox()
    presenter._attention_updates = queue.Queue()

    presenter._drain_updates()

    assert events == [CloseSession("s1")]
    assert presenter._views == {}


def test_voice_capture_popup_establishes_initial_focus_immediately() -> None:
    class Button:
        def configure(self, **_kwargs) -> None:
            pass

    presenter, _events = presenter_with_selection(None)
    view = presenter._views.pop("s1")
    for method in (
        "set_pinned_state",
        "set_title",
        "set_source_preview",
        "set_model",
        "set_loading",
        "configure_standard_actions",
    ):
        setattr(view.surface, method, lambda *_args, **_kwargs: None)
    view.surface.close_button = Button()
    view.surface.pin_button = Button()
    view.surface.configure_back_action = lambda _callback: None
    presenter._create_view = lambda _session_id: view
    requested_initial_focus = []
    presenter._register_view = lambda _session_id, _view, *, focus_on_show=True: requested_initial_focus.append(focus_on_show)

    presenter._apply(SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_LISTENING,
        "voice_input",
        "Voice Input",
        "model",
        status_text="Listening",
    ))

    assert requested_initial_focus == [True]


def test_empty_voice_review_surfaces_the_capture_failure_message() -> None:
    class Button:
        def configure(self, **_kwargs) -> None:
            pass

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    for method in (
        "set_pinned_state",
        "set_title",
        "set_source_preview",
        "set_model",
        "configure_action_contract",
        "configure_back_action",
        "configure_standard_actions",
        "hide_feedback",
    ):
        setattr(view.surface, method, lambda *_args, **_kwargs: None)
    view.surface.close_button = Button()
    view.surface.pin_button = Button()
    view.dialog.flash = lambda _state: None
    target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    presenter._apply(SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "model",
        content="",
        status_text="Voice Input is unavailable on this device.",
        voice_origin=VoiceOrigin(target, "", 0),
    ))

    assert "message:Voice Input is unavailable on this device.:4000" in events


def test_ctrl_v_pastes_only_for_active_popup() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-v>"](None)

    assert result == "break"
    assert events == ["paste:s1"]

    events.clear()
    presenter._popup_control("s1", view).observe_focus(PopupOwnedDialogOpened())
    result = view.dialog.root.bindings["<Control-v>"](None)

    assert result == "break"
    assert events == []


def test_ctrl_v_preserves_native_paste_in_editable_popup_fields() -> None:
    class EditableWidget:
        def winfo_class(self) -> str:
            return "Entry"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal"

    presenter, events = presenter_with_selection(None)
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    result = presenter._paste_shortcut(type("Event", (), {"widget": EditableWidget()})(), "s1")

    assert result is None
    assert events == []


def test_ctrl_v_pastes_external_content_from_editable_voice_review() -> None:
    class EditableVoiceDraft:
        def winfo_class(self) -> str:
            return "Text"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "",
        content="current draft",
    )
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    result = presenter._paste_shortcut(
        type("Event", (), {"widget": EditableVoiceDraft()})(),
        "s1",
    )

    assert result == "break"
    assert events == ["paste:s1"]


def test_voice_draft_intercepts_ctrl_v_before_the_text_widget_can_paste() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay, _callback) -> None:
            pass

    class EditableVoiceDraft:
        def winfo_class(self) -> str:
            return "Text"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    view.last_snapshot = SessionSnapshot(
        "s1", 1, SessionStatus.VOICE_REVIEW, "voice_input", "Voice Input", "model",
        content="reviewed text",
    )
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    presenter._register_view("s1", view)
    result = view.surface.voice_draft_paste_callback(
        type("Event", (), {"state": 0x0004, "widget": EditableVoiceDraft()})()
    )

    assert result == "break"
    assert events == ["paste:s1"]


def test_voice_capture_surface_context_projects_semantic_follow_up_intent() -> None:
    presenter, _events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "model",
    )
    view.surface.selection_range = lambda: (2, 4)

    view.surface.follow_up_visible = True

    assert presenter.voice_capture_surface_context("s1") == VoiceCaptureSurfaceContext(
        "s1",
        follow_up_requested=True,
        selection=(2, 4),
    )


def test_ctrl_enter_switches_voice_draft_mode_without_changing_ctrl_v_paste_intent() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "",
        content="current draft",
    )

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-Return>"](
        type("Event", (), {"state": 0x0004})(),
    )

    assert result == "break"
    assert view.voice_draft_editing is False
    assert events[-2:] == ["voice-editor:False", "voice-mode:False"]

    class VoiceDraftWidget:
        def winfo_class(self) -> str:
            return "Text"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal" if view.voice_draft_editing else "disabled"

    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")
    paste_event = type("Event", (), {"state": 0x0004, "widget": VoiceDraftWidget()})()

    assert view.dialog.root.bindings["<Control-v>"](paste_event) == "break"
    assert events[-1] == "paste:s1"

    assert view.dialog.root.bindings["<Control-Return>"](
        type("Event", (), {"state": 0x0004})(),
    ) == "break"
    paste_count = events.count("paste:s1")
    assert view.dialog.root.bindings["<Control-v>"](paste_event) == "break"
    assert events.count("paste:s1") == paste_count + 1


def test_voice_draft_snapshot_keeps_the_selected_reading_mode() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "",
        content="old draft",
        voice_origin=VoiceOrigin(target, "old draft", 0),
    )
    current = replace(
        previous,
        revision=2,
        content="updated draft",
        voice_origin=VoiceOrigin(target, "updated draft", 1),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.voice_draft_editing = False

    presenter._apply(current)

    assert "voice-content:updated draft" in events
    assert "voice-editor:False" in events
    assert events.index("voice-content:updated draft") < events.index("voice-editor:False")
    assert view.voice_draft_editing is False


def test_finalized_voice_insertion_projects_its_caret_endpoint_once() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_FINALIZING,
        "voice_input",
        "Voice Input",
        "",
        content="hello world",
        voice_origin=VoiceOrigin(target, "hello world", 0),
    )
    insertion = VoiceDraftInsertion(1, 6, 12)
    finalized = replace(
        previous,
        revision=2,
        status=SessionStatus.VOICE_REVIEW,
        content="hello ClipAI",
        voice_origin=VoiceOrigin(target, "hello ClipAI", 1, insertion),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.dialog.lifecycle.schedule = lambda _delay, _callback: "scheduled"

    presenter._apply(finalized)
    presenter._apply(replace(finalized, revision=3, status_text="Ready"))
    next_draft_insertion = VoiceDraftInsertion(4, 0, 4)
    presenter._apply(replace(
        finalized,
        revision=4,
        content="next",
        voice_origin=VoiceOrigin(target, "next", 1, next_draft_insertion),
    ))

    assert events.count("voice-caret:12") == 1
    assert events.count("voice-caret:4") == 1
    assert view.applied_voice_insertion_revision == 4


def test_ctrl_e_toggles_pin_for_active_popup() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    class CtrlWithNumLockEvent:
        state = 0x0004 | 0x0008

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-e>"](CtrlWithNumLockEvent())

    assert result == "break"
    assert events == ["pin:toggled", TogglePin("s1")]

    events.clear()
    presenter._popup_control("s1", view).observe_focus(PopupOwnedDialogOpened())
    result = view.dialog.root.bindings["<Control-e>"](CtrlWithNumLockEvent())

    assert result == "break"
    assert events == []


def test_popup_shortcuts_ignore_alt_modified_global_chords() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    class CtrlAltEvent:
        state = 0x0004 | 0x0008 | 0x00020000

    class CtrlShiftEvent:
        state = 0x0004 | 0x0001

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    presenter._toggle_speech = lambda _session_id: events.append("speech:toggled")
    presenter._copy = lambda _session_id: events.append("copied")
    presenter._archive = lambda _session_id: events.append("archived")

    presenter._register_view("s1", view)

    for event in (CtrlAltEvent(), CtrlShiftEvent()):
        for shortcut in ("<Control-e>", "<Control-q>", "<Control-c>", "<Control-s>"):
            assert view.dialog.root.bindings[shortcut](event) == "break"

    assert events == []


def test_double_clicking_popup_header_toggles_pin() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()

    presenter._register_view("s1", view)
    result = view.surface.header_double_click_callback(None)

    assert result == "break"
    assert events == ["pin:toggled", TogglePin("s1")]


def test_workflow_context_projects_selection_and_displayed_step() -> None:
    presenter, _events = presenter_with_selection("selected")
    presenter._views["s1"].content = "full result"
    presenter._views["s1"].step_id = "step-1"
    context = presenter.workflow_context("s1")
    assert context.workflow_id == "s1"
    assert context.step_id == "step-1"
    assert context.content == "full result"
    assert context.selected_text == "selected"


def test_voice_review_projects_its_draft_as_workflow_context() -> None:
    presenter, _events = presenter_with_selection("selected")
    view = presenter._views["s1"]
    view.content = "voice draft"
    view.step_id = None
    view.last_snapshot = SessionSnapshot("s1", 1, SessionStatus.VOICE_REVIEW, "voice_input", "Voice Input", "", content="voice draft")

    context = presenter.workflow_context("s1")

    assert context is not None
    assert context.step_id == "voice-origin"
    assert context.content == "voice draft"


def test_native_close_request_immediately_excludes_popup_content_and_emits_close_intent() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].content = "full result"
    presenter._views["s1"].step_id = "step-1"

    presenter._request_close("s1")
    presenter._copy("s1")
    presenter._send_text_command("s1", CopyResult)

    assert events == [CloseSession("s1")]
    assert presenter.workflow_context("s1") is None


def test_shortcut_guide_holds_and_restores_the_original_popup_focus() -> None:
    class Guide:
        def show(self, _snapshot) -> None:
            events.append("guide:show")

        def close(self) -> None:
            events.append("guide:close")

    class Lifecycle:
        def schedule(self, _delay_ms, callback) -> str:
            callback()
            return "restore-focus"

        def focus(self) -> None:
            events.append("focus")

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.lifecycle = Lifecycle()
    presenter._shortcut_guide_dialog = Guide()
    presenter._shortcut_guide_focus_return = None

    presenter.show_shortcut_guide(object())

    assert view.surface.focused is False

    presenter.close_shortcut_guide()
    presenter._copy("s1")

    assert events[:3] == ["guide:show", "guide:close", "focus"]
    assert isinstance(events[3], CopyResult)
    assert presenter._popup_control("s1", view).focused_inside is True
    assert view.surface.focused is True


def test_shortcut_guide_does_not_restore_a_popup_that_started_closing() -> None:
    class Guide:
        def show(self, _snapshot) -> None:
            pass

        def close(self) -> None:
            events.append("guide:close")

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    presenter._shortcut_guide_dialog = Guide()
    presenter._shortcut_guide_focus_return = None

    presenter.show_shortcut_guide(object())
    view.close_requested = True
    presenter.close_shortcut_guide()

    assert events == ["guide:close"]
    assert presenter._popup_control("s1", view).focused_inside is False


def test_shortcut_guide_without_an_original_popup_does_not_force_focus() -> None:
    events = []

    class Guide:
        def show(self, _snapshot) -> None:
            events.append("guide:show")

        def close(self) -> None:
            events.append("guide:close")

    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._views = {}
    presenter._shortcut_guide_dialog = Guide()
    presenter._shortcut_guide_focus_hold_active = False
    presenter._shortcut_guide_focus_return = None

    presenter.show_shortcut_guide(object())
    presenter.close_shortcut_guide()

    assert events == ["guide:show", "guide:close"]
    assert presenter._shortcut_guide_focus_return is None


def test_latest_paste_target_updates_visible_focus_projection() -> None:
    presenter, _events = presenter_with_selection(None)
    newer = PasteTarget("hwnd:20", 84, "Writer", "Draft", 2)

    presenter._apply_paste_target(newer)
    presenter._apply_paste_target(PasteTarget("hwnd:10", 42, "Old", "Old", 1))

    surface = presenter._views["s1"].surface
    assert surface.focused is True
    assert surface.paste_target == newer


def test_content_key_ignores_speaking_and_pin_snapshot_changes() -> None:
    snapshot = SessionSnapshot("s1", 0, SessionStatus.COMPLETED, "a", "A", "model", content="long content")
    changed_ui_state = snapshot.evolve(speaking=True, pinned=True)
    assert _content_render_key(changed_ui_state) == _content_render_key(snapshot)


def test_content_key_changes_for_new_content() -> None:
    snapshot = SessionSnapshot("s1", 0, SessionStatus.COMPLETED, "a", "A", "model", content="first")
    changed_content = snapshot.evolve(content="second")
    assert _content_render_key(changed_content) != _content_render_key(snapshot)
