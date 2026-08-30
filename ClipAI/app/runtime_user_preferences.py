from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import (
    GuidancePreferencesCompleted,
    EntryPanelDensityPreferencesCompleted,
    ResetFirstUseHints,
    SetEntryPanelDensity,
    SetFirstUseHintsEnabled,
    SetSpeechSpeed,
    SpeechSpeedPreferencesCompleted,
)
from ClipAI.core.models import EntryPanelDensity, SpeechSpeed, VoiceLanguagePreference
from ClipAI.core.ports import GuidancePreferencesPresenter, OperationTracker, SpeechSpeedPresenter, UserNotifier
from ClipAI.services.user_preferences import UserPreferencesCoordinator, UserPreferencesUpdate


UserPreferencesRuntimeCommand: TypeAlias = (
    SetFirstUseHintsEnabled
    | ResetFirstUseHints
    | GuidancePreferencesCompleted
    | SetSpeechSpeed
    | SpeechSpeedPreferencesCompleted
    | SetEntryPanelDensity
    | EntryPanelDensityPreferencesCompleted
)


class UserPreferencesRuntimeModule:
    """Owns background persistence and projection for user preferences."""

    def __init__(
        self,
        *,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        user_preferences: UserPreferencesCoordinator | None = None,
        guidance_preferences_presenter: GuidancePreferencesPresenter | None = None,
        speech_speed_presenter: SpeechSpeedPresenter | None = None,
        operation_tracker: OperationTracker | None = None,
        notifier: UserNotifier | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._user_preferences = user_preferences
        self._guidance_preferences_presenter = guidance_preferences_presenter
        self._speech_speed_presenter = speech_speed_presenter
        self._operation_tracker = operation_tracker
        self._notifier = notifier

    def handle(self, command: UserPreferencesRuntimeCommand) -> None:
        if isinstance(command, SetFirstUseHintsEnabled):
            self._begin_preference("guidance_enabled", command.operation_id or uuid.uuid4().hex, enabled=command.enabled)
        elif isinstance(command, ResetFirstUseHints):
            self._begin_preference("guidance_reset", command.operation_id or uuid.uuid4().hex)
        elif isinstance(command, SetSpeechSpeed):
            self._begin_preference("speech_speed", command.operation_id or uuid.uuid4().hex, speed=command.speed)
        elif isinstance(command, SetEntryPanelDensity):
            self._begin_preference("entry_panel_density", command.operation_id or uuid.uuid4().hex, density=command.density)
        elif isinstance(command, (GuidancePreferencesCompleted, SpeechSpeedPreferencesCompleted, EntryPanelDensityPreferencesCompleted)):
            if self._user_preferences is not None:
                self._project_preferences(self._user_preferences.complete(command.operation_id, command.error))

    def begin_voice_enabled(self, enabled: bool, operation_id: str, completion: Callable[[str], object]) -> None:
        """Persist one Voice enablement request, then return through its typed caller command."""
        if self._user_preferences is None:
            self._enqueue(completion("Voice Input preferences are unavailable."))
            return
        update = self._user_preferences.begin_set_voice_enabled(enabled, operation_id)
        self._project_preferences(update)
        if update.work is None:
            current = self._user_preferences.voice_preferences
            self._enqueue(completion("" if current.enabled == enabled else "Another settings update is in progress."))
            return
        user_preferences = self._user_preferences
        work = update.work

        def save() -> None:
            self._enqueue(completion(user_preferences.execute(work)))

        self._supervisor.submit(
            f"voice-preferences:{operation_id}",
            save,
            lambda _error: self._enqueue(completion("Could not save Voice Input settings.")),
            task_class="interactive",
        )

    def complete_voice_enabled(self, operation_id: str, error: str = "") -> None:
        if self._user_preferences is not None:
            self._project_preferences(self._user_preferences.complete(operation_id, error))

    def begin_voice_language(self, language: VoiceLanguagePreference, operation_id: str, completion: Callable[[str], object]) -> None:
        if self._user_preferences is None:
            self._enqueue(completion("Voice Input preferences are unavailable."))
            return
        update = self._user_preferences.begin_set_voice_language(language, operation_id)
        self._project_preferences(update)
        if update.work is None:
            current = self._user_preferences.voice_preferences
            self._enqueue(completion("" if current.language == language else "Another settings update is in progress."))
            return
        user_preferences, work = self._user_preferences, update.work

        def save() -> None:
            self._enqueue(completion(user_preferences.execute(work)))

        self._supervisor.submit(
            f"voice-language-preferences:{operation_id}",
            save,
            lambda _error: self._enqueue(completion("Could not save Voice Input language.")),
            task_class="interactive",
        )

    def _begin_preference(
        self,
        kind: str,
        operation_id: str,
        *,
        enabled: bool = False,
        speed: SpeechSpeed | None = None,
        density: EntryPanelDensity | None = None,
    ) -> None:
        if self._user_preferences is None:
            return
        if kind == "guidance_enabled":
            update = self._user_preferences.begin_set_guidance_enabled(enabled, operation_id)
        elif kind == "guidance_reset":
            update = self._user_preferences.begin_reset_guidance(operation_id)
        elif speed is not None:
            update = self._user_preferences.begin_set_speech_speed(speed, operation_id)
        elif density is not None:
            update = self._user_preferences.begin_set_entry_panel_density(density, operation_id)
        else:
            return
        self._project_preferences(update)
        if update.work is None:
            return
        user_preferences = self._user_preferences
        work = update.work
        completion = (
            SpeechSpeedPreferencesCompleted
            if kind == "speech_speed"
            else EntryPanelDensityPreferencesCompleted
            if kind == "entry_panel_density"
            else GuidancePreferencesCompleted
        )
        unexpected_error = (
            "Could not save speech speed. The previous speed remains active."
            if kind == "speech_speed"
            else "Unable to save the Entry Panel view preference. The previous setting remains active."
            if kind == "entry_panel_density"
            else "無法儲存使用引導設定，請再試一次。"
        )

        def save() -> None:
            error = user_preferences.execute(work)
            self._enqueue(completion(operation_id, error))

        self._supervisor.submit(
            f"{'speech-speed-preferences' if kind == 'speech_speed' else 'guidance-preferences'}:{operation_id}",
            save,
            lambda _error: self._enqueue(completion(operation_id, unexpected_error)),
            task_class="interactive",
        )

    def _project_preferences(self, update: UserPreferencesUpdate) -> None:
        if update.ignored:
            return
        if self._guidance_preferences_presenter is not None:
            self._guidance_preferences_presenter.set_guidance_preferences(update.guidance)
        if self._speech_speed_presenter is not None:
            self._speech_speed_presenter.set_speech_speed(update.speech_speed)
        if update.error and self._notifier is not None:
            self._notifier.notify("ClipAI", update.error)
        if update.error and self._operation_tracker is not None:
            self._operation_tracker.report_error(update.error)
