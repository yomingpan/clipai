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


def test_first_success_is_consumed_once_and_survives_restart() -> None:
    store = MemoryStore(UserPreferences(True))
    coordinator = UserPreferencesCoordinator(store)

    assert coordinator.consume_first_use_hint("shorten") is True
    assert coordinator.consume_first_use_hint("shorten") is False
    assert UserPreferencesCoordinator(store).consume_first_use_hint("shorten") is False
    assert store.preferences.seen_action_ids == frozenset({"shorten"})


def test_disabled_guidance_does_not_mark_recipe_seen() -> None:
    store = MemoryStore(UserPreferences(False))
    coordinator = UserPreferencesCoordinator(store)

    assert coordinator.consume_first_use_hint("shorten") is False
    assert store.saved == []


def test_explicit_setting_projects_pending_then_saved_authoritative_state() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(UserPreferences(True)))

    update = coordinator.begin_set_guidance_enabled(False, "op-1")
    assert update.guidance.first_use_hints_enabled is True
    assert update.guidance.update_pending is True
    assert update.work is not None
    assert coordinator.execute(update.work) == ""
    completed = coordinator.complete("op-1")

    assert completed.guidance.first_use_hints_enabled is False
    assert completed.guidance.update_pending is False


def test_failed_setting_keeps_previous_state_and_reports_error() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(UserPreferences(True), fail=True))
    update = coordinator.begin_set_guidance_enabled(False, "op-1")
    assert update.work is not None

    error = coordinator.execute(update.work)
    completed = coordinator.complete("op-1", error)

    assert completed.guidance.first_use_hints_enabled is True
    assert completed.error


def test_reset_only_clears_seen_recipes_without_enabling_hints() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(UserPreferences(False, frozenset({"shorten"}))))
    update = coordinator.begin_reset_guidance("op-1")
    assert update.work is not None
    assert coordinator.execute(update.work) == ""

    completed = coordinator.complete("op-1")
    assert completed.guidance.first_use_hints_enabled is False
    assert completed.guidance.seen_action_ids == frozenset()


def test_seen_write_failure_can_show_again_without_breaking_action() -> None:
    coordinator = UserPreferencesCoordinator(MemoryStore(UserPreferences(True), fail=True))

    assert coordinator.consume_first_use_hint("shorten") is True
    assert coordinator.guidance_preferences.seen_action_ids == frozenset()
