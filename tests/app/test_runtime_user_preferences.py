from types import SimpleNamespace

from ClipAI.app.runtime_user_preferences import UserPreferencesRuntimeModule
from ClipAI.core.models import UserPreferences
from ClipAI.services.user_preferences import UserPreferencesCoordinator


def test_entry_numeric_hint_display_uses_existing_background_preference_gate():
    saved, tasks, commands = [], [], []
    coordinator = UserPreferencesCoordinator(SimpleNamespace(load=lambda: UserPreferences(), save=saved.append))
    module = UserPreferencesRuntimeModule(
        supervisor=SimpleNamespace(submit=lambda identity, work, failed, **kwargs: tasks.append(work)),
        enqueue=commands.append, user_preferences=coordinator,
    )
    assert module.consume_entry_numeric_hint()
    assert saved == []
    assert not module.consume_entry_numeric_hint()
    tasks.pop()()
    assert saved[-1].entry_numeric_hint_count == 1
    module.handle(commands.pop())
    assert module.consume_entry_numeric_hint()
