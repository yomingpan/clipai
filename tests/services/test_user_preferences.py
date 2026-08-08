from __future__ import annotations

from ClipAI.core.models import UserPreferences
from ClipAI.services.user_preferences import UserPreferencesCoordinator


class MemoryStore:
    def __init__(self, preferences: UserPreferences | None = None, *, fail: bool = False) -> None:
        self.preferences = preferences or UserPreferences()
        self.fail = fail
        self.saved: list[UserPreferences] = []

    def load(self) -> UserPreferences:
        return self.preferences

    def save(self, preferences: UserPreferences) -> None:
        if self.fail:
            raise OSError("disk unavailable")
        self.preferences = preferences
        self.saved.append(preferences)


def test_missing_speed_uses_normal_without_rewriting_preferences() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store, base_speech_rate="+0%")

    update = coordinator.begin_set_speech_speed("normal", "speed-1")

    assert coordinator.speech_speed_state.selected_speed == "normal"
    assert coordinator.current_speech_rate() == "+0%"
    assert update.ignored is True
    assert store.saved == []


def test_custom_legacy_rate_is_preserved_until_a_preset_is_saved() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store, base_speech_rate="+12%")

    assert coordinator.speech_speed_state.selected_speed is None
    assert coordinator.current_speech_rate() == "+12%"

    update = coordinator.begin_set_speech_speed("fast", "speed-1")
    assert update.speech_speed.pending_speed == "fast"
    assert coordinator.execute(update.work) == ""
    completed = coordinator.complete("speed-1")

    assert completed.speech_speed.selected_speed == "fast"
    assert completed.speech_speed.pending_speed is None
    assert coordinator.current_speech_rate() == "+25%"
    assert store.preferences.speech_speed == "fast"


def test_failed_speed_save_keeps_authoritative_selection() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(fail=True), base_speech_rate="+0%")
    update = coordinator.begin_set_speech_speed("super_fast", "speed-1")

    assert update.speech_speed.selected_speed == "normal"
    assert update.speech_speed.update_pending is True
    error = coordinator.execute(update.work)
    completed = coordinator.complete("speed-1", error)

    assert completed.speech_speed.selected_speed == "normal"
    assert completed.speech_speed.update_pending is False
    assert completed.error


def test_user_preference_gate_rejects_overlapping_guidance_change() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore())

    speed = coordinator.begin_set_speech_speed("fast", "speed-1")
    guidance = coordinator.begin_set_guidance_enabled(True, "guidance-1")

    assert speed.work is not None
    assert guidance.ignored is True
    assert guidance.guidance.update_pending is True


def test_unavailable_speech_disables_and_rejects_speed_updates() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(), speech_available=False)

    update = coordinator.begin_set_speech_speed("fast", "speed-1")

    assert coordinator.speech_speed_state.available is False
    assert update.ignored is True


def test_stale_completion_cannot_clear_newer_pending_preference() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore())
    coordinator.begin_set_speech_speed("fast", "speed-1")

    stale = coordinator.complete("older")

    assert stale.ignored is True
    assert coordinator.speech_speed_state.pending_speed == "fast"


def test_stale_work_cannot_overwrite_a_newer_preference() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)
    old = coordinator.begin_set_speech_speed("fast", "speed-1").work
    coordinator.complete("speed-1", "cancelled")
    newer = coordinator.begin_set_speech_speed("super_fast", "speed-2").work

    assert coordinator.execute(old) == ""
    assert store.saved == []
    assert coordinator.execute(newer) == ""
    coordinator.complete("speed-2")
    assert coordinator.current_speech_rate() == "+50%"
