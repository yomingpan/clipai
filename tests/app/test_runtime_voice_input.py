from __future__ import annotations

from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.app.runtime_workflows import VoiceCaptureAdmission
from ClipAI.core.commands import DisableVoiceInput, EnableVoiceInput, OpenVoicePermissionSettings, RetryVoiceInputSetup, SetVoiceLanguage, ShortcutPressEnded, ShortcutPressStarted, StartPopupVoiceCapture, StopVoiceCapture, VoiceCaptureCountdownTick, VoiceCaptureCountdownTickForCapture, VoiceCaptureHoldElapsed, VoiceCaptureWatchdogExpired, VoiceDisablePreferenceSaved, VoiceDisableShutdownCompleted, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoiceSilenceWatchdogExpired
from ClipAI.core.models import ControlSurfaceRef, InlineOrigin, PasteOutcome, PasteTarget, ShortcutPressId
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceCapturePhase, VoiceDisableId, VoiceDraftTarget, VoiceEngineEnded, VoiceEngineFinalSegment, VoiceEngineListening, VoiceEngineSetupBlocked, VoiceFollowUpTarget, VoiceLanguage, VoiceLanguageChangeId, VoiceSetupId
from ClipAI.services.voice_input import CancelInlinePaste, DiscardInlineDictation, PresentInlineCopyState, VoiceInputController
from ClipAI.core.commands import CancelInlineDictation, CopyInlineDictation, DismissInlineDictationTerminal, ToggleInlineDictation, ConfirmInlineDictation, InlineDictationCopyCompleted, InlineDictationRefineSettled, InlineDictationRefineCancelAccepted, PasteOperationCompleted


class Engine:
    def __init__(self) -> None:
        self.calls = []
    def prepare(self, setup_id, language) -> None: self.calls.append(("prepare", setup_id, language))
    def start_capture(self, capture_id, language, *, sequence_start=0) -> None: self.calls.append(("start", capture_id, language, sequence_start))
    def stop_capture(self, capture_id) -> None: self.calls.append(("stop", capture_id))
    def cancel_capture(self, capture_id) -> None: self.calls.append(("cancel", capture_id))
    def shutdown(self) -> None: self.calls.append(("shutdown",))
    def reset_permission_profile(self) -> None: self.calls.append(("reset_permission_profile",))


class Workflow:
    def __init__(self, snapshot=None) -> None:
        self.applied = []
        self.follow_up_applied = []
        self.projections = []
        self.snapshot = snapshot or SessionSnapshot("workflow-1", 0, SessionStatus.VOICE_REVIEW, "voice_input", "Voice Input", "model")
    def apply_voice_finalization(self, target, text, message="") -> None: self.applied.append((target, text, message))
    def apply_voice_follow_up_finalization(self, capture_id, target, text, message="") -> None: self.follow_up_applied.append((capture_id, target, text, message))
    def project_voice_capture(self, projection) -> None: self.projections.append(projection)
    def restore_voice_review(self, _target, _message) -> None: pass
    def restore_voice_follow_up(self, _capture_id, _target, _message) -> None: pass


class Workflows:
    def __init__(self) -> None: self.created = []; self.controllers = {}
    def create_voice_workflow(self, workflow_id, target):
        self.created.append((workflow_id, target)); self.controllers[workflow_id] = Workflow()
    def controller_for(self, workflow_id): return self.controllers.get(workflow_id)
    def _voice_review_target(self, workflow_id):
        return VoiceDraftTarget(workflow_id, 0, PasteTarget("hwnd:1", 1, "Editor", "private", 1), 2, 2)
    def admit_voice_capture(self, intent):
        if intent.trigger == "popup":
            workflow = self.controllers.get(intent.workflow_id)
            if workflow is None:
                return VoiceCaptureAdmission("rejected")
            snapshot = workflow.snapshot
            if snapshot.status is SessionStatus.VOICE_REVIEW:
                return VoiceCaptureAdmission(
                    "voice_review",
                    workflow_id=intent.workflow_id,
                    target=self._voice_review_target(intent.workflow_id),
                )
            if (
                snapshot.status in {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED}
                and snapshot.active_invocation_id is None
                and "follow_up" in snapshot.available_actions
            ):
                return VoiceCaptureAdmission(
                    "follow_up",
                    workflow_id=intent.workflow_id,
                    target=VoiceFollowUpTarget(intent.workflow_id),
                )
            return VoiceCaptureAdmission("rejected", workflow_id=intent.workflow_id)
        if intent.focused_surface is not None and intent.focused_surface.kind == "workflow":
            return VoiceCaptureAdmission(
                "voice_review",
                workflow_id=intent.focused_surface.surface_id,
                target=self._voice_review_target(intent.focused_surface.surface_id),
            )
        return VoiceCaptureAdmission("create")


class RejectedWorkflows(Workflows):
    def admit_voice_capture(self, _intent):
        return VoiceCaptureAdmission(
            "rejected",
            workflow_id="pinned-workflow",
            message="目前此內容無法使用語音輸入",
        )


class ContinuingWorkflows(Workflows):
    def admit_voice_capture(self, _intent):
        return VoiceCaptureAdmission("continue", workflow_id="pinned-workflow")


class FollowUpWorkflows(Workflows):
    def __init__(self) -> None:
        super().__init__()
        self.controllers["result-workflow"] = Workflow(SessionSnapshot(
            "result-workflow",
            4,
            SessionStatus.COMPLETED,
            "summarize",
            "Summarize",
            "model",
            content="answer",
            available_actions=("copy", "follow_up"),
        ))

    def admit_voice_capture(self, _intent):
        return VoiceCaptureAdmission(
            "follow_up",
            workflow_id="result-workflow",
            target=VoiceFollowUpTarget("result-workflow"),
        )


class Setup:
    def __init__(self) -> None: self.shown = 0; self.closed = 0; self.projections = []
    def show_voice_setup(self) -> None: self.shown += 1
    def close_voice_setup(self) -> None: self.closed += 1
    def set_voice_projection(self, projection) -> None: self.projections.append(projection)


class Notifier:
    def __init__(self) -> None: self.messages = []
    def notify(self, title, message) -> None: self.messages.append((title, message))


class InlinePresenter:
    def __init__(self):
        self.opened = 0
        self.modes = []
        self.placements = []
        self.interaction_ids = []
        self.choices = []
        self.choice_messages = []
        self.closed = []
        self.projections = []
        self.paste_outcomes = []
        self.paste_pending = []
        self.paste_cancelling = []
        self.refining = []
        self.refinement_pending = []
        self.cancel_unconfirmed = []
        self.recoveries = []
        self.copy_states = []

    def open_inline_dictation(self, interaction_id="", mode="choice", placement="cursor"): self.opened += 1; self.modes.append(mode); self.placements.append(placement); self.interaction_ids.append(interaction_id)
    def update_inline_dictation(self, projection): self.projections.append(projection)
    def present_inline_choice(self, _interaction_id, text, allow_refine=True, message=""): self.choices.append(text); self.choice_messages.append(message)
    def present_inline_paste_outcome(self, interaction_id, outcome, text): self.paste_outcomes.append((interaction_id, outcome, text))
    def present_inline_paste_pending(self, interaction_id): self.paste_pending.append(interaction_id)
    def present_inline_paste_cancelling(self, interaction_id): self.paste_cancelling.append(interaction_id)
    def present_inline_refining(self, interaction_id): self.refining.append(interaction_id)
    def present_inline_refinement_pending(self, interaction_id): self.refinement_pending.append(interaction_id)
    def present_inline_cancel_unconfirmed(self, interaction_id, text): self.cancel_unconfirmed.append((interaction_id, text))
    def present_inline_recovery(self, interaction_id, text, message): self.recoveries.append((interaction_id, text, message))
    def present_inline_copy_state(self, interaction_id, state): self.copy_states.append((interaction_id, state))
    def close_inline_dictation(self, *, flash_failure=False, message="", interaction_id=""):
        self.closed.append((flash_failure, message))


def test_inline_target_is_frozen_at_start_and_choice_blocks_restart():
    engine, presenter, pasted = Engine(), InlinePresenter(), []
    target = PasteTarget("hwnd:1", 1, "Editor", "private", 1)
    reader = [target]
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: reader[0], inline_presenter=presenter,
        paste_inline=lambda text, captured, refine, _interaction_id, _operation_id: pasted.append((text, captured, refine)),
    )

    assert runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    assert presenter.interaction_ids[0] != str(capture)
    reader[0] = None
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    assert runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    assert presenter.choices == ["spoken words"]
    assert not runtime.handle(ToggleInlineDictation())
    assert runtime.handle(ConfirmInlineDictation(presenter.interaction_ids[0]))
    assert pasted == [("spoken words", target, False)]


def test_inline_stage_log_links_separate_ids_without_content_or_target_title(caplog) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="clipai.inline_trace")
    engine, presenter = Engine(), InlinePresenter()
    target = PasteTarget("hwnd:1", 1, "Editor", "private target title", 1)
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: target, inline_presenter=presenter,
    )
    assert runtime.handle(ToggleInlineDictation())
    capture_id = engine.calls[-1][1]
    interaction_id = presenter.interaction_ids[0]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture_id)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture_id, 0, "private dictated words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture_id)))

    trace = "\n".join(record.getMessage() for record in caplog.records if record.name == "clipai.inline_trace")
    assert f"interaction_id={interaction_id}" in trace
    assert f"capture_id={capture_id}" in trace
    assert "stage=listening" in trace
    assert "stage=recognition_settled" in trace
    assert "stage=choice_ready" in trace
    assert "monotonic_ns=" in trace
    assert "private dictated words" not in trace
    assert "private target title" not in trace


def test_inline_recovery_trace_records_only_outcomes(caplog) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="clipai.inline_trace")
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=Engine(), workflows=Workflows(),
        paste_target_reader=lambda: None, inline_presenter=InlinePresenter(),
    )
    runtime._execute_effect(PresentInlineCopyState("interaction-1", "succeeded"))
    runtime._execute_effect(DiscardInlineDictation("interaction-1", "Voice Input cancellation timed out."))

    trace = "\n".join(record.getMessage() for record in caplog.records if record.name == "clipai.inline_trace")
    assert "stage=copy_result interaction_id=interaction-1" in trace
    assert "outcome=succeeded" in trace
    assert "stage=discard_terminal interaction_id=interaction-1" in trace
    assert "outcome=failed" in trace
    assert "Voice Input cancellation timed out." not in trace


def test_minimal_mode_is_frozen_at_start_and_second_press_selects_raw_or_refine():
    for stop_press_type, expected_refine in (("short", False), ("long", True)):
        engine, presenter, requests = Engine(), InlinePresenter(), []
        selected_mode = ["minimal"]
        runtime = VoiceInputRuntimeModule(
            controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
            paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
            inline_input_mode_reader=lambda: selected_mode[0],
            inline_presenter=presenter,
            paste_inline=lambda *args: requests.append(args),
        )
        assert runtime.handle(ToggleInlineDictation("short"))
        selected_mode[0] = "choice"
        capture = engine.calls[-1][1]
        runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
        assert runtime.handle(ToggleInlineDictation(stop_press_type))
        runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))

        assert presenter.modes == ["minimal"]
        assert presenter.choices == []
        assert len(requests) == 1
        assert requests[0][2] is expected_refine


def test_inline_placement_is_read_when_interaction_opens() -> None:
    presenter = InlinePresenter()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=Engine(), workflows=Workflows(),
        paste_target_reader=lambda: None,
        inline_dictation_placement_reader=lambda: "bottom_center",
        inline_presenter=presenter,
    )
    assert runtime.handle(ToggleInlineDictation("short"))
    assert presenter.placements == ["bottom_center"]


def test_inline_without_target_preserves_text_without_offering_paste_choice():
    engine, presenter = Engine(), InlinePresenter()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: None, inline_presenter=presenter,
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))

    assert presenter.choices == []
    assert presenter.recoveries[0][:2] == (presenter.interaction_ids[0], "spoken words")
    assert presenter.closed == []


def test_inline_does_not_reuse_a_stale_foreground_target_when_capture_probe_fails() -> None:
    engine, presenter, pasted = Engine(), InlinePresenter(), []
    stale = PasteTarget("hwnd:old", 1, "Previous editor", "private", 1)
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: stale,
        capture_external_target=lambda: None,
        inline_presenter=presenter,
        paste_inline=lambda *args: pasted.append(args),
    )
    assert runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))

    assert presenter.recoveries[0][:2] == (presenter.interaction_ids[0], "spoken words")
    assert presenter.choices == []
    assert pasted == []


def test_inline_recovery_copy_is_explicit_and_reports_matching_completion() -> None:
    engine, presenter, copies = Engine(), InlinePresenter(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: None, inline_presenter=presenter,
        copy_inline=lambda *args: copies.append(args),
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "complete original text")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    interaction_id = presenter.interaction_ids[0]

    assert runtime.handle(CopyInlineDictation(interaction_id))
    assert copies[0][:2] == ("complete original text", interaction_id)
    assert presenter.copy_states[-1] == (interaction_id, "pending")
    assert not runtime.handle(CopyInlineDictation(interaction_id))
    assert not runtime.handle(InlineDictationCopyCompleted(interaction_id, "stale"))
    assert runtime.handle(InlineDictationCopyCompleted(interaction_id, copies[0][2]))
    assert presenter.copy_states[-1] == (interaction_id, "succeeded")


def test_cancel_inline_choice_closes_without_pasting():
    engine, presenter, pasted = Engine(), InlinePresenter(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        paste_inline=lambda text, target, refine, _interaction_id, _operation_id: pasted.append(text),
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))

    assert runtime.cancel_inline_dictation()
    assert not runtime.handle(ConfirmInlineDictation(presenter.interaction_ids[0]))
    assert pasted == []
    assert presenter.closed[-1] == (False, "")


def test_stale_view_commands_cannot_confirm_or_cancel_the_new_interaction() -> None:
    engine, presenter, pasted = Engine(), InlinePresenter(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        paste_inline=lambda *args: pasted.append(args),
    )
    assert runtime.handle(ToggleInlineDictation())
    old_id = presenter.interaction_ids[-1]
    old_capture = engine.calls[-1][1]
    assert runtime.handle(CancelInlineDictation(old_id))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(old_capture)))

    assert runtime.handle(ToggleInlineDictation())
    new_id = presenter.interaction_ids[-1]
    new_capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(new_capture, 0, "new text")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(new_capture)))

    assert old_id != new_id
    closed_before = list(presenter.closed)
    assert not runtime.handle(ConfirmInlineDictation(old_id))
    assert not runtime.handle(CancelInlineDictation(old_id))
    assert presenter.closed == closed_before
    assert pasted == []
    assert runtime.handle(ConfirmInlineDictation(new_id))
    assert pasted[0][0] == "new text"


def test_inline_capture_cancel_remains_visible_until_engine_settles() -> None:
    engine, presenter = Engine(), InlinePresenter()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
    )
    assert runtime.handle(ToggleInlineDictation())
    capture_id = engine.calls[-1][1]
    interaction_id = presenter.interaction_ids[-1]

    assert runtime.handle(CancelInlineDictation(interaction_id))
    assert engine.calls[-1] == ("cancel", capture_id)
    assert presenter.projections[-1].capture_phase is VoiceCapturePhase.CANCEL_REQUESTED
    assert presenter.closed == []
    assert not runtime.handle(ToggleInlineDictation())

    assert runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture_id)))
    assert presenter.closed == [(False, "")]
    assert not runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture_id)))
    assert presenter.closed == [(False, "")]


def test_inline_capture_cancel_watchdog_reports_timeout_and_closes_once() -> None:
    engine, presenter = Engine(), InlinePresenter()
    scheduled, dispatched = [], []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        watchdog_schedule=lambda delay, callback: scheduled.append((delay, callback)),
        dispatch=dispatched.append,
    )
    assert runtime.handle(ToggleInlineDictation())
    capture_id = engine.calls[-1][1]
    interaction_id = presenter.interaction_ids[-1]
    assert runtime.handle(CancelInlineDictation(interaction_id))
    assert presenter.closed == []

    callback = next(callback for delay, callback in scheduled if delay == 6.0)
    callback()
    assert presenter.closed == []
    assert len(dispatched) == 1
    assert runtime.handle(dispatched.pop())
    assert presenter.closed == [(True, "Voice Input cancellation timed out.")]
    assert not runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture_id)))
    assert len(presenter.closed) == 1


def test_inline_cancel_and_discard_effects_forward_their_frozen_interaction() -> None:
    class Presenter(InlinePresenter):
        def __init__(self) -> None:
            super().__init__()
            self.close_ids = []

        def close_inline_dictation(self, *, flash_failure=False, message="", interaction_id=""):
            self.close_ids.append(interaction_id)

    presenter = Presenter()
    cancelled = []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=Engine(), workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        cancel_inline_paste=cancelled.append,
    )
    assert runtime.handle(ToggleInlineDictation())
    current_id = presenter.interaction_ids[0]

    runtime._execute_effect(CancelInlinePaste("paste-old", "inline-old"))
    runtime._execute_effect(DiscardInlineDictation("inline-old"))

    assert current_id != "inline-old"
    assert presenter.paste_cancelling == ["inline-old"]
    assert cancelled == ["paste-old"]
    assert presenter.close_ids == ["inline-old"]


def test_discard_during_refinement_quarantines_late_provider_result():
    engine, presenter, requested = Engine(), InlinePresenter(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        paste_inline=lambda *args: requested.append(args),
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    interaction_id = presenter.interaction_ids[0]
    assert runtime.handle(ConfirmInlineDictation(interaction_id, True))
    assert len(requested) == 1
    assert not runtime.handle(ToggleInlineDictation())
    assert runtime.cancel_inline_dictation()
    refine_operation_id = requested[0][4]
    assert runtime.handle(InlineDictationRefineSettled(interaction_id, "late refined words", operation_id=refine_operation_id))
    assert len(requested) == 1


def test_refinement_escape_requests_provider_cancel_and_waits_for_typed_admission():
    engine, presenter, requested, dispatched, cancelled = Engine(), InlinePresenter(), [], [], []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter, paste_inline=lambda *args: requested.append(args),
        cancel_inline_refinement=lambda operation_id: cancelled.append(operation_id) or True,
        dispatch=dispatched.append,
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    runtime.handle(ConfirmInlineDictation(presenter.interaction_ids[0], True))
    operation_id = requested[0][4]

    assert runtime.cancel_inline_dictation()
    assert cancelled == [operation_id]
    interaction_id = presenter.interaction_ids[0]
    assert presenter.paste_cancelling == [interaction_id]
    assert not runtime.handle(ToggleInlineDictation())
    assert dispatched == [InlineDictationRefineCancelAccepted(interaction_id, operation_id, True)]
    assert runtime.handle(dispatched.pop())
    assert not runtime.handle(InlineDictationRefineSettled(interaction_id, "late", operation_id=operation_id))
    assert runtime.handle(ToggleInlineDictation())


def test_refinement_failure_reopens_original_text_and_never_pastes_fallback():
    engine, presenter, requested = Engine(), InlinePresenter(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        paste_inline=lambda *args: requested.append(args),
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    assert runtime.handle(ConfirmInlineDictation(presenter.interaction_ids[0], True))
    assert runtime.handle(InlineDictationRefineSettled(presenter.interaction_ids[0], error=True, operation_id=requested[0][4]))
    assert presenter.choices == ["spoken words", "spoken words"]
    assert len(requested) == 1
    assert not runtime.handle(ToggleInlineDictation())


def test_refinement_timeout_reaches_recovery_and_content_safe_trace(caplog):
    engine, presenter, requested = Engine(), InlinePresenter(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter,
        paste_inline=lambda *args: requested.append(args) or True,
    )
    caplog.set_level("INFO", logger="clipai.inline_trace")
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "private spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    interaction_id = presenter.interaction_ids[0]
    runtime.handle(ConfirmInlineDictation(interaction_id, True))

    assert runtime.handle(InlineDictationRefineSettled(
        interaction_id, error=True, operation_id=requested[0][4], failure_reason="timed_out"
    ))

    assert presenter.choices[-1] == "private spoken words"
    assert presenter.choice_messages[-1].startswith("Dictation refinement timed out.")
    assert len(requested) == 1
    assert "stage=refine_settled" in caplog.text
    assert "outcome=timed_out" in caplog.text
    assert "private spoken words" not in caplog.text


def test_refining_state_waits_for_provider_task_admission():
    for admitted in (False, True):
        engine, presenter = Engine(), InlinePresenter()
        runtime = VoiceInputRuntimeModule(
            controller=VoiceInputController(enabled=True), engine=engine, workflows=Workflows(),
            paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
            inline_presenter=presenter,
            paste_inline=lambda *_args: admitted,
        )
        runtime.handle(ToggleInlineDictation())
        capture = engine.calls[-1][1]
        runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
        runtime.handle(ToggleInlineDictation())
        runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
        assert runtime.handle(ConfirmInlineDictation(presenter.interaction_ids[0], True))

        assert presenter.refinement_pending == [presenter.interaction_ids[0]]
        assert presenter.refining == ([presenter.interaction_ids[0]] if admitted else [])


def test_inline_paste_terminal_requires_matching_operation_and_keeps_uncertain_truth_visible():
    engine, presenter, requests = Engine(), InlinePresenter(), []
    controller = VoiceInputController(enabled=True)
    runtime = VoiceInputRuntimeModule(
        controller=controller, engine=engine, workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        inline_presenter=presenter, paste_inline=lambda *args: requests.append(args),
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))
    assert runtime.handle(ConfirmInlineDictation(presenter.interaction_ids[0]))
    interaction_id = presenter.interaction_ids[0]
    operation_id = controller.inline_paste_operation_id(interaction_id)
    assert operation_id is not None
    assert presenter.paste_pending == [interaction_id]
    assert not runtime.handle(ToggleInlineDictation())

    outcome = PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored")
    assert not runtime.handle_inline_paste_completion(PasteOperationCompleted("stale", "", outcome, InlineOrigin(interaction_id)))
    assert not runtime.handle_inline_paste_completion(PasteOperationCompleted(operation_id, "", outcome, InlineOrigin("other")))
    assert runtime.handle_inline_paste_completion(PasteOperationCompleted(operation_id, "", outcome, InlineOrigin(interaction_id)))
    assert presenter.paste_outcomes == [(interaction_id, outcome, "spoken words")]
    assert not runtime.handle_inline_paste_completion(PasteOperationCompleted(operation_id, "", outcome, InlineOrigin(interaction_id)))
    assert runtime.handle(ToggleInlineDictation())
    assert not runtime.handle(DismissInlineDictationTerminal(interaction_id))
    assert len(engine.calls) >= 3


def test_pending_inline_choice_rejects_ptt_before_workflow_admission():
    engine, workflows = Engine(), Workflows()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True), engine=engine, workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
    )
    runtime.handle(ToggleInlineDictation())
    capture = engine.calls[-1][1]
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture, 0, "spoken words")))
    runtime.handle(ToggleInlineDictation())
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture)))

    assert not runtime.handle_shortcut_started(ShortcutPressStarted(99, "voice_input"))
    assert workflows.created == []


def test_active_voice_capture_rejects_entry_panel_open_with_feedback() -> None:
    notifier = Notifier()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=Engine(),
        workflows=Workflows(),
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        notifier=notifier,
    )
    runtime.handle_shortcut_started(
        ShortcutPressStarted(ShortcutPressId(1), "voice_input")
    )

    assert runtime.admit_entry_panel_open() is False
    assert notifier.messages
    assert "Voice Input is active" in notifier.messages[-1][1]


class Watchdog:
    def __init__(self, callback) -> None: self.callback = callback; self.cancelled = False
    def cancel(self) -> None: self.cancelled = True


def test_ptt_opens_the_microphone_only_after_the_hold_threshold() -> None:
    engine, workflows, scheduled = Engine(), Workflows(), []

    def hold_schedule(delay, callback):
        timer = Watchdog(callback)
        scheduled.append((delay, timer))
        return timer

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        hold_schedule=hold_schedule,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(41, "voice_input")) is True
    assert len(workflows.created) == 1
    assert engine.calls == []
    assert scheduled[0][0] == 0.18

    assert runtime.handle(VoiceCaptureHoldElapsed(41)) is True
    assert scheduled[0][1].cancelled is True
    assert engine.calls == [("start", "voice-press-41", "zh-TW", 0)]


def test_ptt_quick_tap_never_opens_the_microphone_and_keeps_the_draft() -> None:
    engine, workflows, scheduled = Engine(), Workflows(), []

    def hold_schedule(delay, callback):
        timer = Watchdog(callback)
        scheduled.append(timer)
        return timer

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        hold_schedule=hold_schedule,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(42, "voice_input")) is True
    assert runtime.handle_shortcut_ended(
        ShortcutPressEnded(42, "voice_input", "released")
    ) is True

    assert scheduled[0].cancelled is True
    assert engine.calls == []
    assert len(workflows.created) == 1


def test_voice_shutdown_cancels_an_armed_hold_before_its_late_callback() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []

    def hold_schedule(_delay, callback):
        timer = Watchdog(callback)
        scheduled.append(timer)
        return timer

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        dispatch=dispatched.append,
        hold_schedule=hold_schedule,
    )
    runtime.handle_shortcut_started(ShortcutPressStarted(43, "voice_input"))

    runtime.stop()
    scheduled[0].callback()

    assert scheduled[0].cancelled is True
    assert dispatched == []
    assert engine.calls == [("shutdown",)]


def test_ptt_flow_creates_workflow_after_admission_and_applies_finalized_text() -> None:
    engine, workflows = Engine(), Workflows()
    controller = VoiceInputController(enabled=True)
    target = PasteTarget("hwnd:1", 1, "Editor", "private", 1)
    runtime = VoiceInputRuntimeModule(controller=controller, engine=engine, workflows=workflows, paste_target_reader=lambda: target)
    press = ShortcutPressStarted(1, "voice_input")

    assert runtime.handle_shortcut_started(press) is True
    capture_id = "voice-press-1"
    assert runtime.handle(VoiceCaptureHoldElapsed(1)) is True
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(capture_id)))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(capture_id, 0, "hello")))
    runtime.handle_shortcut_ended(ShortcutPressEnded(1, "voice_input", "released"))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(capture_id)))

    assert engine.calls[0] == ("start", capture_id, "zh-TW", 0)
    assert engine.calls[1] == ("stop", capture_id)
    workflow_id = workflows.created[0][0]
    assert workflows.controllers[workflow_id].applied[0][1] == "hello"


def test_ptt_captures_the_current_external_target_when_the_cached_target_is_missing() -> None:
    engine, workflows = Engine(), Workflows()
    cached_target = None
    current_target = PasteTarget("hwnd:2", 2, "Writer", "Draft", 2)
    captured = []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: cached_target,
        capture_external_target=lambda: captured.append(True) or current_target,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(2, "voice_input")) is True
    assert captured == [True]
    assert workflows.created[0][1] == current_target
    assert engine.calls == []
    assert runtime.handle(VoiceCaptureHoldElapsed(2)) is True
    assert engine.calls == [("start", "voice-press-2", "zh-TW", 0)]


def test_ptt_without_an_external_target_starts_a_targetless_voice_draft() -> None:
    engine, workflows, notifier = Engine(), Workflows(), Notifier()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        notifier=notifier,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(3, "voice_input")) is True
    assert workflows.created[0][1] is None
    assert engine.calls == []
    assert runtime.handle(VoiceCaptureHoldElapsed(3)) is True
    assert engine.calls == [("start", "voice-press-3", "zh-TW", 0)]
    assert notifier.messages == []


def test_pinned_voice_rejection_does_not_capture_an_external_target_or_start_the_engine() -> None:
    engine, workflows, notifier, captured = Engine(), RejectedWorkflows(), Notifier(), []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        capture_external_target=lambda: captured.append(True) or None,
        notifier=notifier,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(30, "voice_input")) is False
    assert captured == []
    assert workflows.created == []
    assert engine.calls == []
    assert notifier.messages == [("Voice Input", "目前此內容無法使用語音輸入")]


def test_active_pinned_voice_shortcut_is_consumed_without_creating_a_second_capture() -> None:
    engine, workflows = Engine(), ContinuingWorkflows()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(31, "voice_input")) is True
    assert workflows.created == []
    assert engine.calls == []


def test_ptt_over_a_completed_result_finalizes_into_its_follow_up() -> None:
    engine, workflows = Engine(), FollowUpWorkflows()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(33, "voice_input")) is True
    assert runtime.handle(VoiceCaptureHoldElapsed(33)) is True
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment("voice-press-33", 0, "What changed?")))
    runtime.handle_shortcut_ended(ShortcutPressEnded(33, "voice_input", "released"))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded("voice-press-33")))

    workflow = workflows.controllers["result-workflow"]
    assert workflows.created == []
    assert workflow.follow_up_applied[0][2] == "What changed?"


def test_disable_waits_for_persisted_preference_after_engine_shutdown() -> None:
    engine, workflows, dispatched, persisted = Engine(), Workflows(), [], []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        persist_disabled=persisted.append,
        dispatch=dispatched.append,
    )
    disable = VoiceDisableId("disable-1")

    assert runtime.handle(DisableVoiceInput(disable)) is True
    assert engine.calls == [("shutdown",)]
    assert persisted == [disable]
    assert dispatched == [VoiceDisableShutdownCompleted(disable)]
    assert runtime.handle(dispatched.pop()) is True
    assert runtime.handle(VoiceDisablePreferenceSaved(disable)) is True


def test_unready_ptt_opens_setup_without_creating_a_workflow_or_capture() -> None:
    engine, workflows, setup = Engine(), Workflows(), Setup()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        setup_presenter=setup,
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(1, "voice_input")) is True
    assert setup.shown == 1
    assert workflows.created == []
    assert engine.calls == []


def test_ptt_from_voice_review_reuses_its_workflow_and_frozen_selection() -> None:
    engine, workflows = Engine(), Workflows()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        focused_surface_reader=lambda: ControlSurfaceRef("voice-workflow", "workflow"),
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(4, "voice_input")) is True
    assert workflows.created == []
    assert engine.calls == []
    assert runtime.handle(VoiceCaptureHoldElapsed(4)) is True
    assert engine.calls == [("start", "voice-press-4", "zh-TW", 0)]


def test_closing_the_capture_workflow_cancels_its_engine_capture() -> None:
    engine, workflows = Engine(), Workflows()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
    )
    runtime.handle_shortcut_started(ShortcutPressStarted(5, "voice_input"))
    runtime.handle(VoiceCaptureHoldElapsed(5))

    assert runtime.close_workflow(workflows.created[0][0]) is True
    assert engine.calls[-1] == ("cancel", "voice-press-5")


def test_setup_permission_blocked_stays_visible_with_authoritative_projection() -> None:
    engine, workflows, setup = Engine(), Workflows(), Setup()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        setup_presenter=setup,
    )
    operation = VoiceSetupId("setup-1")

    runtime.handle(EnableVoiceInput(operation))
    assert runtime.handle(VoiceEngineEventReceived(VoiceEngineSetupBlocked(operation))) is True

    assert setup.projections[-1].capability is VoiceCapabilityPhase.PERMISSION_BLOCKED


def test_voice_language_save_failure_notifies_and_keeps_previous_language() -> None:
    notifier = Notifier()
    projections = []
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=Engine(),
        workflows=Workflows(),
        paste_target_reader=lambda: None,
        persist_language=lambda _operation_id, _language: None,
        projection_sink=projections.append,
        notifier=notifier,
    )
    change = VoiceLanguageChangeId("language-1")

    assert runtime.handle(SetVoiceLanguage(VoiceLanguage("en-US"), change)) is True
    assert projections[-1].pending_language == "en-US"
    assert runtime.handle(VoiceLanguagePreferenceSaved(change, "Could not save Voice Input language.")) is True
    assert projections[-1].language == "zh-TW"
    assert projections[-1].pending_language is None
    assert notifier.messages == [("Voice Input", "Could not save Voice Input language.")]
    assert runtime.handle(VoiceLanguagePreferenceSaved(change, "stale error")) is False
    assert len(notifier.messages) == 1


def test_permission_repair_resets_only_the_voice_profile_before_retrying_setup() -> None:
    engine, workflows, setup = Engine(), Workflows(), Setup()
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        setup_presenter=setup,
    )
    blocked = VoiceSetupId("blocked-setup")
    retry = VoiceSetupId("repair-setup")

    runtime.handle(EnableVoiceInput(blocked))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineSetupBlocked(blocked)))

    assert runtime.handle(RetryVoiceInputSetup(retry)) is True
    assert engine.calls == [
        ("prepare", blocked, "zh-TW"),
        ("reset_permission_profile",),
        ("prepare", retry, "zh-TW"),
    ]
    assert setup.projections[-1].capability is VoiceCapabilityPhase.REQUESTING_PERMISSION


def test_permission_settings_intent_does_not_mutate_voice_state() -> None:
    engine, workflows, opened = Engine(), Workflows(), []
    controller = VoiceInputController()
    runtime = VoiceInputRuntimeModule(
        controller=controller,
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        open_permission_settings=lambda: opened.append(True),
    )

    assert runtime.handle(OpenVoicePermissionSettings()) is True
    assert opened == [True]
    assert controller.projection.capability is VoiceCapabilityPhase.SETUP_REQUIRED
    assert engine.calls == []


def test_ptt_time_limit_starts_after_listening_and_saves_the_finalized_section() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []
    now = [100.0]

    def schedule(delay, callback):
        watchdog = Watchdog(callback)
        scheduled.append((delay, watchdog))
        return watchdog

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        dispatch=dispatched.append,
        watchdog_schedule=schedule,
        monotonic_clock=lambda: now[0],
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(9, "voice_input")) is True
    assert scheduled == []
    assert runtime.handle(VoiceCaptureHoldElapsed(9)) is True
    assert runtime.handle(VoiceEngineEventReceived(VoiceEngineListening("voice-press-9"))) is True
    assert scheduled[0][0] == 120.0
    scheduled[0][1].callback()
    assert dispatched == []
    now[0] = 220.0
    scheduled[0][1].callback()
    assert dispatched == [VoiceCaptureWatchdogExpired(9)]
    assert runtime.handle(dispatched.pop()) is True
    assert any(delay == 6.0 and not timer.cancelled for delay, timer in scheduled)
    assert [timer for delay, timer in scheduled if delay == 120.0][-1].cancelled
    assert engine.calls[-1] == ("stop", "voice-press-9")
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment("voice-press-9", 0, "keep this thought")))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded("voice-press-9")))
    assert workflows.controllers[workflows.created[0][0]].applied[-1][1:] == (
        "keep this thought",
        "The 2-minute Voice Input limit was reached. This section was saved; release the shortcut and press it again to continue.",
    )


def test_ptt_countdown_uses_the_same_listening_deadline_as_the_safety_limit() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []
    now = [100.0]

    def schedule(delay, callback):
        watchdog = Watchdog(callback)
        scheduled.append((delay, watchdog))
        return watchdog

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        dispatch=dispatched.append,
        watchdog_schedule=schedule,
        monotonic_clock=lambda: now[0],
    )
    runtime.handle_shortcut_started(ShortcutPressStarted(11, "voice_input"))
    runtime.handle(VoiceCaptureHoldElapsed(11))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening("voice-press-11")))

    assert scheduled[0][0] == 120.0
    assert scheduled[1][0] == 1.0
    assert workflows.controllers[workflows.created[0][0]].projections[-1].remaining_seconds == 120

    now[0] = 101.2
    scheduled[1][1].callback()
    assert dispatched == [VoiceCaptureCountdownTick(11, 119)]
    assert runtime.handle(dispatched.pop()) is True
    assert workflows.controllers[workflows.created[0][0]].projections[-1].remaining_seconds == 119


def test_ptt_release_cancels_watchdog_before_a_late_callback_can_cancel_again() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []

    def schedule(_delay, callback):
        watchdog = Watchdog(callback)
        scheduled.append(watchdog)
        return watchdog

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: PasteTarget("hwnd:1", 1, "Editor", "private", 1),
        dispatch=dispatched.append,
        watchdog_schedule=schedule,
    )
    runtime.handle_shortcut_started(ShortcutPressStarted(10, "voice_input"))
    runtime.handle(VoiceCaptureHoldElapsed(10))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening("voice-press-10")))

    assert runtime.handle_shortcut_ended(ShortcutPressEnded(10, "voice_input", "released")) is True
    assert scheduled[0].cancelled is True
    scheduled[0].callback()
    assert dispatched == []
    assert engine.calls == [("start", "voice-press-10", "zh-TW", 0), ("stop", "voice-press-10")]


def test_popup_voice_capture_reuses_completed_workflow_and_finalizes_into_follow_up() -> None:
    engine, workflows = Engine(), Workflows()
    workflow = Workflow(SessionSnapshot(
        "workflow-1",
        4,
        SessionStatus.COMPLETED,
        "summarize",
        "Summarize",
        "model",
        content="answer",
        available_actions=("copy", "follow_up"),
    ))
    workflows.controllers["workflow-1"] = workflow
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
    )

    assert runtime.handle(StartPopupVoiceCapture("workflow-1", "capture-1")) is True
    runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment("capture-1", 0, "What changed?")))
    runtime.handle(StopVoiceCapture("capture-1"))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded("capture-1")))

    assert workflows.created == []
    assert engine.calls == [
        ("start", "capture-1", "zh-TW", 0),
        ("stop", "capture-1"),
    ]
    assert workflow.follow_up_applied[0][0] == "capture-1"
    assert workflow.follow_up_applied[0][2] == "What changed?"


def test_popup_voice_capture_is_rejected_while_provider_is_active() -> None:
    engine, workflows = Engine(), Workflows()
    workflows.controllers["workflow-1"] = Workflow(SessionSnapshot(
        "workflow-1",
        4,
        SessionStatus.REQUESTING_PROVIDER,
        "summarize",
        "Summarize",
        "model",
        active_invocation_id="provider-1",
    ))
    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
    )

    assert runtime.handle(StartPopupVoiceCapture("workflow-1", "capture-1")) is False
    assert engine.calls == []


def test_listening_schedules_non_terminal_two_second_silence_hint() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []
    workflow = Workflow(SessionSnapshot(
        "workflow-1",
        4,
        SessionStatus.COMPLETED,
        "summarize",
        "Summarize",
        "model",
        available_actions=("follow_up",),
    ))
    workflows.controllers["workflow-1"] = workflow

    def schedule(delay, callback):
        watchdog = Watchdog(callback)
        scheduled.append((delay, watchdog))
        return watchdog

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        dispatch=dispatched.append,
        watchdog_schedule=schedule,
    )
    runtime.handle(StartPopupVoiceCapture("workflow-1", "capture-1"))

    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening("capture-1")))

    silence_watchdog = next(watchdog for delay, watchdog in scheduled if delay == 2.0)
    silence_watchdog.callback()
    assert dispatched == [VoiceSilenceWatchdogExpired("capture-1")]
    assert runtime.handle(dispatched.pop()) is True
    assert workflow.projections[-1].silence_detected is True


def test_popup_countdown_at_29_seconds_does_not_stop_capture() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []
    workflow = Workflow(SessionSnapshot(
        "workflow-1",
        4,
        SessionStatus.COMPLETED,
        "summarize",
        "Summarize",
        "model",
        available_actions=("follow_up",),
    ))
    workflows.controllers["workflow-1"] = workflow

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        dispatch=dispatched.append,
        watchdog_schedule=lambda delay, callback: Watchdog(callback),
    )
    runtime.handle(StartPopupVoiceCapture("workflow-1", "capture-1"))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening("capture-1")))

    assert runtime.handle(VoiceCaptureCountdownTickForCapture("capture-1", 29)) is True
    assert engine.calls == [("start", "capture-1", "zh-TW", 0)]
    assert workflow.projections[-1].remaining_seconds == 29


def test_popup_deadline_rechecks_early_timer_and_late_callback_is_inert_after_stop() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []
    now = [100.0]
    workflows.controllers["workflow-1"] = Workflow(SessionSnapshot(
        "workflow-1",
        4,
        SessionStatus.COMPLETED,
        "summarize",
        "Summarize",
        "model",
        available_actions=("follow_up",),
    ))

    def schedule(delay, callback):
        watchdog = Watchdog(callback)
        scheduled.append((delay, watchdog))
        return watchdog

    runtime = VoiceInputRuntimeModule(
        controller=VoiceInputController(enabled=True),
        engine=engine,
        workflows=workflows,
        paste_target_reader=lambda: None,
        dispatch=dispatched.append,
        watchdog_schedule=schedule,
        monotonic_clock=lambda: now[0],
    )
    runtime.handle(StartPopupVoiceCapture("workflow-1", "capture-1"))
    runtime.handle(VoiceEngineEventReceived(VoiceEngineListening("capture-1")))
    expiry = next(watchdog for delay, watchdog in scheduled if delay == 120.0)

    expiry.callback()
    assert dispatched == []
    rescheduled_expiry = scheduled[-1][1]

    assert runtime.handle(StopVoiceCapture("capture-1")) is True
    assert rescheduled_expiry.cancelled is True
    now[0] = 220.0
    rescheduled_expiry.callback()
    assert dispatched == []
