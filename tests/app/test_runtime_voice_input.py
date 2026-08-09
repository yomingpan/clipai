from __future__ import annotations

from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.core.commands import DisableVoiceInput, EnableVoiceInput, ShortcutPressEnded, ShortcutPressStarted, VoiceDisablePreferenceSaved, VoiceDisableShutdownCompleted, VoiceEngineEventReceived
from ClipAI.core.models import ControlSurfaceRef, PasteTarget
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceDisableId, VoiceDraftTarget, VoiceEngineEnded, VoiceEngineFinalSegment, VoiceEngineListening, VoiceEngineSetupBlocked, VoiceSetupId
from ClipAI.services.voice_input import VoiceInputController


class Engine:
    def __init__(self) -> None:
        self.calls = []
    def prepare(self, setup_id, language) -> None: self.calls.append(("prepare", setup_id, language))
    def start_capture(self, capture_id, language, *, sequence_start=0) -> None: self.calls.append(("start", capture_id, language, sequence_start))
    def stop_capture(self, capture_id) -> None: self.calls.append(("stop", capture_id))
    def cancel_capture(self, capture_id) -> None: self.calls.append(("cancel", capture_id))
    def shutdown(self) -> None: self.calls.append(("shutdown",))


class Workflow:
    def __init__(self) -> None: self.applied = []
    def apply_voice_finalization(self, target, text) -> None: self.applied.append((target, text))
    def project_voice_capture(self, _projection) -> None: pass
    def restore_voice_review(self, _target, _message) -> None: pass


class Workflows:
    def __init__(self) -> None: self.created = []; self.controllers = {}
    def create_voice_workflow(self, workflow_id, target):
        self.created.append((workflow_id, target)); self.controllers[workflow_id] = Workflow()
    def controller_for(self, workflow_id): return self.controllers.get(workflow_id)
    def capture_target_for_voice_review(self, workflow_id):
        return VoiceDraftTarget(workflow_id, 0, PasteTarget("hwnd:1", 1, "Editor", "private", 1), 2, 2)


class Setup:
    def __init__(self) -> None: self.shown = 0; self.closed = 0; self.projections = []
    def show_voice_setup(self) -> None: self.shown += 1
    def close_voice_setup(self) -> None: self.closed += 1
    def set_voice_projection(self, projection) -> None: self.projections.append(projection)


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
