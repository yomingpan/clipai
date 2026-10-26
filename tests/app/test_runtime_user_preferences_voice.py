from __future__ import annotations

from ClipAI.app.runtime_user_preferences import UserPreferencesRuntimeModule
from ClipAI.core.commands import InlineInputModePreferencesCompleted, SetInlineInputMode
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


class InlineModePresenter:
    def __init__(self) -> None:
        self.states = []

    def set_inline_input_mode(self, state) -> None:
        self.states.append(state)


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


def test_inline_mode_uses_shared_save_gate_and_projects_only_saved_selection() -> None:
    store, supervisor, enqueued, presenter = Store(), Supervisor(), [], InlineModePresenter()
    module = UserPreferencesRuntimeModule(
        supervisor=supervisor,
        enqueue=enqueued.append,
        user_preferences=UserPreferencesCoordinator(store),
        inline_input_mode_presenter=presenter,
    )

    module.handle(SetInlineInputMode("minimal", "mode-1"))
    assert presenter.states[-1].selected_mode == "choice"
    assert presenter.states[-1].pending_mode == "minimal"
    task = next(work for task_id, work in supervisor.work.items() if task_id.endswith(":mode-1"))
    task()
    assert enqueued == [InlineInputModePreferencesCompleted("mode-1")]
    module.handle(enqueued.pop())
    assert presenter.states[-1].selected_mode == "minimal"
    assert presenter.states[-1].pending_mode is None
