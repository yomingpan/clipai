from __future__ import annotations

import json

from ClipAI.core.models import GuidancePreferences
from ClipAI.platform.guidance_preferences import JsonGuidancePreferencesStore


def test_preferences_default_disabled_when_file_is_missing(tmp_path) -> None:
    store = JsonGuidancePreferencesStore(tmp_path / "preferences.json")
    assert store.load() == GuidancePreferences()


def test_preferences_round_trip_with_schema_and_no_temporary_file(tmp_path) -> None:
    path = tmp_path / "data" / "preferences.json"
    store = JsonGuidancePreferencesStore(path)
    expected = GuidancePreferences(False, frozenset({"translate", "shorten"}))

    store.save(expected)

    assert store.load() == expected
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 2,
        "first_use_hints_enabled": False,
        "seen_action_ids": ["shorten", "translate"],
    }
    assert list(path.parent.glob("*.tmp")) == []


def test_invalid_or_future_preferences_fall_back_safely(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    store = JsonGuidancePreferencesStore(path)
    path.write_text("[]", encoding="utf-8")
    assert store.load() == GuidancePreferences()
    path.write_text('{"schema_version": 3}', encoding="utf-8")
    assert store.load() == GuidancePreferences()


def test_v1_preferences_disable_old_default_but_preserve_seen_actions(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    store = JsonGuidancePreferencesStore(path)
    path.write_text(
        '{"schema_version": 1, "first_use_hints_enabled": true, "seen_action_ids": ["shorten"]}',
        encoding="utf-8",
    )

    assert store.load() == GuidancePreferences(False, frozenset({"shorten"}))
