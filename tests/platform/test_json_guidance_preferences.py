from __future__ import annotations

import json

from ClipAI.core.models import UserPreferences
from ClipAI.platform.user_preferences import JsonUserPreferencesStore


def test_preferences_default_disabled_when_file_is_missing(tmp_path) -> None:
    store = JsonUserPreferencesStore(tmp_path / "preferences.json")
    assert store.load() == UserPreferences()


def test_preferences_round_trip_with_schema_and_no_temporary_file(tmp_path) -> None:
    path = tmp_path / "data" / "preferences.json"
    store = JsonUserPreferencesStore(path)
    expected = UserPreferences(False, frozenset({"translate", "shorten"}), "fast")

    store.save(expected)

    assert store.load() == expected
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 3,
        "first_use_hints_enabled": False,
        "seen_action_ids": ["shorten", "translate"],
        "speech_speed": "fast",
    }
    assert list(path.parent.glob("*.tmp")) == []


def test_invalid_or_future_preferences_fall_back_safely(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    store = JsonUserPreferencesStore(path)
    path.write_text("[]", encoding="utf-8")
    assert store.load() == UserPreferences()
    path.write_text('{"schema_version": 4}', encoding="utf-8")
    assert store.load() == UserPreferences()


def test_v1_preferences_disable_old_default_but_preserve_seen_actions(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    store = JsonUserPreferencesStore(path)
    path.write_text(
        '{"schema_version": 1, "first_use_hints_enabled": true, "seen_action_ids": ["shorten"]}',
        encoding="utf-8",
    )

    assert store.load() == UserPreferences(False, frozenset({"shorten"}))


def test_v2_preferences_preserve_guidance_without_creating_a_speech_override(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    store = JsonUserPreferencesStore(path)
    path.write_text(
        '{"schema_version": 2, "first_use_hints_enabled": true, "seen_action_ids": ["shorten"]}',
        encoding="utf-8",
    )

    assert store.load() == UserPreferences(True, frozenset({"shorten"}), None)


def test_invalid_speech_speed_does_not_discard_valid_guidance_preferences(tmp_path) -> None:
    path = tmp_path / "preferences.json"
    store = JsonUserPreferencesStore(path)
    path.write_text(
        '{"schema_version": 3, "first_use_hints_enabled": true, "seen_action_ids": ["shorten"], "speech_speed": "turbo"}',
        encoding="utf-8",
    )

    assert store.load() == UserPreferences(True, frozenset({"shorten"}), None)
