from __future__ import annotations

from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.core.commands import DisableVoiceInput, ShortcutPressEnded, ShortcutPressStarted, VoiceDisablePreferenceSaved, VoiceDisableShutdownCompleted, VoiceEngineEventReceived
from ClipAI.core.models import PasteTarget
from ClipAI.core.voice import VoiceDisableId, VoiceEngineEnded, VoiceEngineFinalSegment, VoiceEngineListening, VoiceSetupId
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


class Workflows:
    def __init__(self) -> None: self.created = []; self.controllers = {}
    def create_voice_workflow(self, workflow_id, target):
        self.created.append((workflow_id, target)); self.controllers[workflow_id] = Workflow()
    def controller_for(self, workflow_id): return self.controllers.get(workflow_id)


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
