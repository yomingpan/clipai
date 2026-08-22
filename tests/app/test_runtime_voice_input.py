from __future__ import annotations

from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.app.runtime_workflows import VoiceCaptureAdmission
from ClipAI.core.commands import DisableVoiceInput, EnableVoiceInput, OpenVoicePermissionSettings, RetryVoiceInputSetup, ShortcutPressEnded, ShortcutPressStarted, StartPopupVoiceCapture, StopVoiceCapture, VoiceCaptureWatchdogExpired, VoiceDisablePreferenceSaved, VoiceDisableShutdownCompleted, VoiceEngineEventReceived, VoiceSilenceWatchdogExpired
from ClipAI.core.models import ControlSurfaceRef, PasteTarget
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceDisableId, VoiceDraftTarget, VoiceEngineEnded, VoiceEngineFinalSegment, VoiceEngineListening, VoiceEngineSetupBlocked, VoiceFollowUpTarget, VoiceSetupId
from ClipAI.services.voice_input import VoiceInputController


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
    def apply_voice_finalization(self, target, text) -> None: self.applied.append((target, text))
    def apply_voice_follow_up_finalization(self, capture_id, target, text) -> None: self.follow_up_applied.append((capture_id, target, text))
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


class Watchdog:
    def __init__(self, callback) -> None: self.callback = callback; self.cancelled = False
    def cancel(self) -> None: self.cancelled = True


def test_ptt_flow_creates_workflow_after_admission_and_applies_finalized_text() -> None:
    engine, workflows = Engine(), Workflows()
    controller = VoiceInputController(enabled=True)
    target = PasteTarget("hwnd:1", 1, "Editor", "private", 1)
    runtime = VoiceInputRuntimeModule(controller=controller, engine=engine, workflows=workflows, paste_target_reader=lambda: target)
    press = ShortcutPressStarted(1, "voice_input")

    assert runtime.handle_shortcut_started(press) is True
    capture_id = "voice-press-1"
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


def test_missing_ptt_release_is_cancelled_by_its_watchdog() -> None:
    engine, workflows, dispatched, scheduled = Engine(), Workflows(), [], []

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
    )

    assert runtime.handle_shortcut_started(ShortcutPressStarted(9, "voice_input")) is True
    assert scheduled[0][0] == 120.0
    scheduled[0][1].callback()
    assert dispatched == [VoiceCaptureWatchdogExpired(9)]
    assert runtime.handle(dispatched.pop()) is True
    assert scheduled[0][1].cancelled is True
    assert engine.calls[-1] == ("cancel", "voice-press-9")


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

    assert runtime.handle_shortcut_ended(ShortcutPressEnded(10, "voice_input", "released")) is True
    assert scheduled[0].cancelled is True
    scheduled[0].callback()
    assert runtime.handle(dispatched.pop()) is False
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

    assert scheduled[0][0] == 2.0
    scheduled[0][1].callback()
    assert dispatched == [VoiceSilenceWatchdogExpired("capture-1")]
    assert runtime.handle(dispatched.pop()) is True
    assert workflow.projections[-1].silence_detected is True
