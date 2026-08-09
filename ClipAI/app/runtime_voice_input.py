from __future__ import annotations

import uuid
from collections.abc import Callable

from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.core.commands import CancelVoiceCapture, DisableVoiceInput, EnableVoiceInput, OpenVoiceSetup, SetVoiceLanguage, ShortcutPressEnded, ShortcutPressStarted, StopVoiceCapture, UpdateVoiceDraft, VoiceDisableShutdownCompleted, VoiceDisablePreferenceSaved, VoiceEngineEventReceived, VoiceLanguagePreferenceSaved, VoicePreferenceSaved
from ClipAI.core.models import ControlSurfaceRef, PasteTarget
from ClipAI.core.ports import VoiceInputEngine, VoiceSetupPresenter
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceDraftTarget, VoiceLanguageChangeId, VoiceProjection
from ClipAI.services.voice_input import CancelVoiceCapture as CancelVoiceCaptureEffect
from ClipAI.services.voice_input import FinalizeVoiceDraft, PersistVoiceDisabled, PersistVoiceEnabled, PersistVoiceLanguage, PrepareVoiceSetup, RestoreVoiceReview, ShutdownVoiceEngine, StartVoiceCapture, StopVoiceCapture as StopVoiceCaptureEffect, VoiceEffect, VoiceInputController, VoiceTransition


class VoiceInputRuntimeModule:
    """Routes typed Voice effects without retaining Voice domain state."""

    def __init__(
        self,
        *,
        controller: VoiceInputController,
        engine: VoiceInputEngine,
        workflows: WorkflowRuntimeModule,
        paste_target_reader: Callable[[], PasteTarget | None],
        persist_enabled: Callable[[str], None] = lambda _setup_id: None,
        persist_disabled: Callable[[str], None] = lambda _disable_id: None,
        persist_language: Callable[[str, str], None] = lambda _operation_id, _language: None,
        complete_voice_preference: Callable[[str, str], None] = lambda _operation_id, _error: None,
        dispatch: Callable[[object], None] = lambda _command: None,
        projection_sink: Callable[[VoiceProjection], None] = lambda _projection: None,
        setup_presenter: VoiceSetupPresenter | None = None,
        focused_surface_reader: Callable[[], ControlSurfaceRef | None] = lambda: None,
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._workflows = workflows
        self._paste_target_reader = paste_target_reader
        self._persist_enabled = persist_enabled
        self._persist_disabled = persist_disabled
        self._persist_language = persist_language
        self._complete_voice_preference = complete_voice_preference
        self._dispatch = dispatch
        self._projection_sink = projection_sink
        self._setup_presenter = setup_presenter
        self._focused_surface_reader = focused_surface_reader

    def handle_shortcut_started(self, command: ShortcutPressStarted) -> bool:
        focused_surface = self._focused_surface_reader()
        if focused_surface is not None:
            if focused_surface.kind != "workflow":
                return False
            target = self._workflows.capture_target_for_voice_review(focused_surface.surface_id)
            if target is None:
                return False
            transition = self._controller.request_capture_for_press(command.press_id, target)
            if transition.ignored:
                return False
            self._execute(transition)
            return True
        if self._controller.projection.capability is VoiceCapabilityPhase.SETUP_REQUIRED:
            if self._setup_presenter is not None:
                self._setup_presenter.show_voice_setup()
            return True
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

    def close_workflow(self, workflow_id: str) -> bool:
        transition = self._controller.cancel_capture_for_workflow(workflow_id)
        if transition.ignored:
            return False
        self._execute(transition)
        return True

    def handle(self, command: OpenVoiceSetup | EnableVoiceInput | DisableVoiceInput | VoiceDisableShutdownCompleted | VoiceDisablePreferenceSaved | VoiceEngineEventReceived | VoicePreferenceSaved | StopVoiceCapture | CancelVoiceCapture | SetVoiceLanguage | VoiceLanguagePreferenceSaved | UpdateVoiceDraft) -> bool:
        if isinstance(command, OpenVoiceSetup):
            if self._setup_presenter is not None:
                self._setup_presenter.show_voice_setup()
            return True
        if isinstance(command, EnableVoiceInput):
            transition = self._controller.request_setup(command.setup_id)
        elif isinstance(command, DisableVoiceInput):
            transition = self._controller.request_disable(command.disable_id)
        elif isinstance(command, VoiceDisableShutdownCompleted):
            transition = self._controller.complete_disable_shutdown(command.disable_id, command.error)
        elif isinstance(command, VoiceDisablePreferenceSaved):
            self._complete_voice_preference(command.disable_id, command.error)
            transition = self._controller.complete_disable_preference(command.disable_id, command.error)
        elif isinstance(command, VoiceEngineEventReceived):
            transition = self._controller.observe_engine(command.event)
        elif isinstance(command, VoicePreferenceSaved):
            self._complete_voice_preference(command.setup_id, command.error)
            transition = self._controller.complete_enable_save(command.setup_id, command.error)
        elif isinstance(command, StopVoiceCapture):
            transition = self._controller.request_stop(command.capture_id)
        elif isinstance(command, SetVoiceLanguage):
            operation_id = command.operation_id or VoiceLanguageChangeId(uuid.uuid4().hex)
            transition = self._controller.set_language(command.language, operation_id)
        elif isinstance(command, VoiceLanguagePreferenceSaved):
            self._complete_voice_preference(command.operation_id, command.error)
            transition = self._controller.complete_language_save(command.operation_id, command.error)
        elif isinstance(command, UpdateVoiceDraft):
            controller = self._workflows.controller_for(command.workflow_id)
            return controller is not None and controller.edit_voice_draft(command.expected_revision, command.text) is not None
        else:
            transition = self._controller.request_cancel(command.capture_id)
        if transition.ignored:
            return False
        self._execute(transition)
        return True

    def stop(self) -> None:
        self._engine.shutdown()

    def _execute(self, transition: VoiceTransition) -> None:
        self._projection_sink(transition.projection)
        if self._setup_presenter is not None:
            self._setup_presenter.set_voice_projection(transition.projection)
        if transition.projection.capability is VoiceCapabilityPhase.READY and self._setup_presenter is not None:
            self._setup_presenter.close_voice_setup()
        if transition.projection.workflow_id is not None:
            controller = self._workflows.controller_for(transition.projection.workflow_id)
            if controller is not None:
                controller.project_voice_capture(transition.projection)
        for effect in transition.effects:
            self._execute_effect(effect)

    def _execute_effect(self, effect: VoiceEffect) -> None:
        if isinstance(effect, PrepareVoiceSetup):
            self._engine.prepare(effect.setup_id, effect.language)
        elif isinstance(effect, PersistVoiceEnabled):
            self._persist_enabled(effect.setup_id)
        elif isinstance(effect, PersistVoiceDisabled):
            self._persist_disabled(effect.disable_id)
        elif isinstance(effect, PersistVoiceLanguage):
            self._persist_language(effect.operation_id, effect.language)
        elif isinstance(effect, ShutdownVoiceEngine):
            try:
                self._engine.shutdown()
            except Exception as exc:
                self._dispatch(VoiceDisableShutdownCompleted(effect.disable_id, str(exc)))
            else:
                self._dispatch(VoiceDisableShutdownCompleted(effect.disable_id))
        elif isinstance(effect, StartVoiceCapture):
            self._engine.start_capture(effect.capture_id, effect.language, sequence_start=effect.sequence_start)
        elif isinstance(effect, StopVoiceCaptureEffect):
            self._engine.stop_capture(effect.capture_id)
        elif isinstance(effect, CancelVoiceCaptureEffect):
            self._engine.cancel_capture(effect.capture_id)
        elif isinstance(effect, RestoreVoiceReview):
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.restore_voice_review(effect.target, effect.message)
        else:
            controller = self._workflows.controller_for(effect.target.workflow_id)
            if controller is not None:
                controller.apply_voice_finalization(effect.target, effect.text)
