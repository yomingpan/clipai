from __future__ import annotations

from ClipAI.core.models import GuidancePreferences
from ClipAI.services.guidance_preferences import GuidancePreferencesCoordinator


class MemoryStore:
    def __init__(self, preferences: GuidancePreferences | None = None, *, fail: bool = False) -> None:
        self.preferences = preferences or GuidancePreferences()
        self.fail = fail
        self.saved: list[GuidancePreferences] = []

    def load(self) -> GuidancePreferences:
        return self.preferences

    def save(self, preferences: GuidancePreferences) -> None:
        if self.fail:
            raise OSError("disk unavailable")
        self.preferences = preferences
        self.saved.append(preferences)


def test_first_success_is_consumed_once_and_survives_restart() -> None:
    store = MemoryStore(GuidancePreferences(True))
    coordinator = GuidancePreferencesCoordinator(store)

    assert coordinator.consume_first_use_hint("shorten") is True
    assert coordinator.consume_first_use_hint("shorten") is False
    assert GuidancePreferencesCoordinator(store).consume_first_use_hint("shorten") is False
    assert store.preferences.seen_action_ids == frozenset({"shorten"})


def test_disabled_guidance_does_not_mark_recipe_seen() -> None:
    store = MemoryStore(GuidancePreferences(False))
    coordinator = GuidancePreferencesCoordinator(store)

    assert coordinator.consume_first_use_hint("shorten") is False
    assert store.saved == []


def test_explicit_setting_projects_pending_then_saved_authoritative_state() -> None:
    coordinator = GuidancePreferencesCoordinator(MemoryStore(GuidancePreferences(True)))

    update = coordinator.begin_set_enabled(False, "op-1")
    assert update.preferences.first_use_hints_enabled is True
    assert update.preferences.update_pending is True
    assert update.work is not None
    assert coordinator.execute(update.work) == ""
    completed = coordinator.complete("op-1")

    assert completed.preferences.first_use_hints_enabled is False
    assert completed.preferences.update_pending is False


def test_failed_setting_keeps_previous_state_and_reports_error() -> None:
    coordinator = GuidancePreferencesCoordinator(MemoryStore(GuidancePreferences(True), fail=True))
    update = coordinator.begin_set_enabled(False, "op-1")
    assert update.work is not None

    error = coordinator.execute(update.work)
    completed = coordinator.complete("op-1", error)

    assert completed.preferences.first_use_hints_enabled is True
    assert completed.error


def test_reset_only_clears_seen_recipes_without_enabling_hints() -> None:
    coordinator = GuidancePreferencesCoordinator(MemoryStore(GuidancePreferences(False, frozenset({"shorten"}))))
    update = coordinator.begin_reset("op-1")
    assert update.work is not None
    assert coordinator.execute(update.work) == ""

    completed = coordinator.complete("op-1")
    assert completed.preferences.first_use_hints_enabled is False
    assert completed.preferences.seen_action_ids == frozenset()


def test_seen_write_failure_can_show_again_without_breaking_action() -> None:
    coordinator = GuidancePreferencesCoordinator(MemoryStore(GuidancePreferences(True), fail=True))

    assert coordinator.consume_first_use_hint("shorten") is True
    assert coordinator.preferences.seen_action_ids == frozenset()
