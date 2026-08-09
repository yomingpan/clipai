from __future__ import annotations

import uuid
from collections.abc import Callable

from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.core.commands import CancelVoiceCapture, EnableVoiceInput, ShortcutPressEnded, ShortcutPressStarted, StopVoiceCapture, VoiceEngineEventReceived
from ClipAI.core.models import PasteTarget
from ClipAI.core.ports import VoiceInputEngine
from ClipAI.core.voice import VoiceDraftTarget
from ClipAI.services.voice_input import CancelVoiceCapture as CancelVoiceCaptureEffect
from ClipAI.services.voice_input import FinalizeVoiceDraft, PrepareVoiceSetup, StartVoiceCapture, StopVoiceCapture as StopVoiceCaptureEffect, VoiceEffect, VoiceInputController, VoiceTransition


class VoiceInputRuntimeModule:
    """Routes typed Voice effects without retaining Voice domain state."""

    def __init__(
        self,
        *,
        controller: VoiceInputController,
        engine: VoiceInputEngine,
        workflows: WorkflowRuntimeModule,
        paste_target_reader: Callable[[], PasteTarget | None],
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._workflows = workflows
        self._paste_target_reader = paste_target_reader

    def handle_shortcut_started(self, command: ShortcutPressStarted) -> bool:
        target = self._paste_target_reader()
        if target is None:
            return False
        workflow_id = uuid.uuid4().hex
        frozen = VoiceDraftTarget(workflow_id, 0, target, 0, 0)
        transition = self._controller.request_capture_for_press(command.press_id, frozen)
        if transition.ignored:
            return False
        self._workflows.create_voice_workflow(workflow_id, target)
        self._execute(transition)
        return True

    def handle_shortcut_ended(self, command: ShortcutPressEnded) -> bool:
        transition = (
            self._controller.abandon_press(command.press_id)
            if command.outcome == "cancelled"
            else self._controller.request_release_for_press(command.press_id)
        )
        if transition.ignored:
            return False
        self._execute(transition)
        return True

    def handle(self, command: EnableVoiceInput | VoiceEngineEventReceived | StopVoiceCapture | CancelVoiceCapture) -> bool:
        if isinstance(command, EnableVoiceInput):
            transition = self._controller.request_setup(command.setup_id)
        elif isinstance(command, VoiceEngineEventReceived):
            transition = self._controller.observe_engine(command.event)
        elif isinstance(command, StopVoiceCapture):
            transition = self._controller.request_stop(command.capture_id)
        else:
            transition = self._controller.request_cancel(command.capture_id)
        if transition.ignored:
            return False
        self._execute(transition)
        return True

    def stop(self) -> None:
        self._engine.shutdown()

    def _execute(self, transition: VoiceTransition) -> None:
        for effect in transition.effects:
            self._execute_effect(effect)

    def _execute_effect(self, effect: VoiceEffect) -> None:
        if isinstance(effect, PrepareVoiceSetup):
            self._engine.prepare(effect.setup_id, effect.language)
        elif isinstance(effect, StartVoiceCapture):
            self._engine.start_capture(effect.capture_id, effect.language, sequence_start=effect.sequence_start)
        elif isinstance(effect, StopVoiceCaptureEffect):
            self._engine.stop_capture(effect.capture_id)
        elif isinstance(effect, CancelVoiceCaptureEffect):
            self._engine.cancel_capture(effect.capture_id)
        else:
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.apply_voice_finalization(effect.target, effect.text)
