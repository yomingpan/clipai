from __future__ import annotations

from ClipAI.app.runtime_user_preferences import UserPreferencesRuntimeModule
from ClipAI.core.models import UserPreferences
from ClipAI.core.voice import VoiceSetupId
from ClipAI.services.user_preferences import UserPreferencesCoordinator


class Store:
    def __init__(self) -> None:
        self.preferences = UserPreferences()

    def load(self) -> UserPreferences:
        return self.preferences

    def save(self, preferences: UserPreferences) -> None:
        self.preferences = preferences


class Supervisor:
    def __init__(self) -> None:
        self.work: dict[str, object] = {}

    def submit(self, task_id, work, _on_error, **_kwargs) -> None:
        self.work[task_id] = work


def test_voice_preference_persistence_releases_the_shared_preference_gate() -> None:
    store, supervisor, enqueued = Store(), Supervisor(), []
    module = UserPreferencesRuntimeModule(
        supervisor=supervisor,
        enqueue=enqueued.append,
        user_preferences=UserPreferencesCoordinator(store),
    )
    setup = VoiceSetupId("setup-1")

    module.begin_voice_enabled(True, setup, lambda error: (setup, error))
    supervisor.work["voice-preferences:setup-1"]()

    assert enqueued == [(setup, "")]
    module.complete_voice_enabled(setup)
    module.begin_voice_enabled(False, "disable-1", lambda error: ("disable-1", error))

    assert "voice-preferences:disable-1" in supervisor.work
