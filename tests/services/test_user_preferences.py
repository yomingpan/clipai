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


def test_inline_mode_becomes_active_only_after_successful_atomic_save() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)
    update = coordinator.begin_set_inline_input_mode("minimal", "mode-1")

    assert update.inline_input_mode.selected_mode == "choice"
    assert update.inline_input_mode.pending_mode == "minimal"
    assert coordinator.inline_input_mode == "choice"
    assert coordinator.execute(update.work) == ""
    assert coordinator.inline_input_mode == "minimal"
    assert coordinator.complete("mode-1").inline_input_mode.selected_mode == "minimal"


def test_inline_placement_rejects_invalid_or_unchanged_values_without_saving() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)
    assert coordinator.begin_set_inline_dictation_placement("invalid", "bad").ignored is True
    assert coordinator.begin_set_inline_dictation_placement("cursor", "same").ignored is True
    assert store.saved == []
    assert coordinator.inline_dictation_placement_state.update_pending is False


def test_inline_placement_projects_pending_and_commits_only_after_save() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)
    update = coordinator.begin_set_inline_dictation_placement("bottom_center", "placement-1")
    assert update.inline_dictation_placement.selected_placement == "cursor"
    assert update.inline_dictation_placement.pending_placement == "bottom_center"
    assert update.inline_dictation_placement.update_pending is True
    assert coordinator.inline_dictation_placement == "cursor"
    assert coordinator.execute(update.work) == ""
    assert coordinator.inline_dictation_placement == "bottom_center"
    completed = coordinator.complete("placement-1")
    assert completed.inline_dictation_placement.selected_placement == "bottom_center"
    assert completed.inline_dictation_placement.update_pending is False


def test_inline_placement_save_failure_preserves_previous_selection() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(fail=True))
    update = coordinator.begin_set_inline_dictation_placement("bottom_center", "placement-1")
    error = coordinator.execute(update.work)
    assert error == "Could not save Inline Dictation placement. The previous placement remains active."
    assert coordinator.complete("placement-1", error).inline_dictation_placement.selected_placement == "cursor"


def test_failed_inline_mode_save_keeps_choice_and_clears_pending_on_completion() -> None:
    store = MemoryStore(fail=True)
    coordinator = UserPreferencesCoordinator(store)
    update = coordinator.begin_set_inline_input_mode("minimal", "mode-1")
    error = coordinator.execute(update.work)

    assert error
    assert coordinator.inline_input_mode == "choice"
    completed = coordinator.complete("mode-1", error)
    assert completed.inline_input_mode.selected_mode == "choice"
    assert completed.inline_input_mode.pending_mode is None


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


def test_voice_enablement_and_language_use_the_existing_single_preference_gate() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)
    enabled = coordinator.begin_set_voice_enabled(True, "voice-enable")

    assert enabled.voice.enabled is False
    assert enabled.voice.update_pending is True
    assert coordinator.begin_set_voice_language("en-US", "voice-language").ignored is True
    assert coordinator.execute(enabled.work) == ""
    coordinator.complete("voice-enable")
    assert coordinator.voice_preferences.enabled is True

    language = coordinator.begin_set_voice_language("en-US", "voice-language")
    assert coordinator.execute(language.work) == ""
    coordinator.complete("voice-language")
    assert coordinator.voice_preferences.language == "en-US"


def test_entry_panel_density_uses_the_existing_preference_gate() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)

    update = coordinator.begin_set_entry_panel_density("compact", "panel-density")

    assert update.work is not None
    assert coordinator.execute(update.work) == ""
    coordinator.complete("panel-density")
    assert coordinator.entry_panel_density == "compact"
    assert store.preferences.entry_panel_density == "compact"


def test_newer_entry_panel_density_replaces_an_unsettled_density_write() -> None:
    store = MemoryStore()
    coordinator = UserPreferencesCoordinator(store)
    compact = coordinator.begin_set_entry_panel_density("compact", "compact")
    detailed = coordinator.begin_set_entry_panel_density("detailed", "detailed")

    assert coordinator.execute(compact.work) == ""
    assert store.saved == []
    assert coordinator.execute(detailed.work) == ""
    coordinator.complete("detailed")
    assert coordinator.entry_panel_density == "detailed"
