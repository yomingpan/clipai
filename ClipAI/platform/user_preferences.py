from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import cast

from ClipAI.core.models import SpeechSpeed, UserPreferences

_SPEECH_SPEEDS: frozenset[str] = frozenset({"slow", "normal", "fast", "super_fast"})


class JsonUserPreferencesStore:
    def __init__(self, path: str | Path = "data/user_preferences.json") -> None:
        self._path = Path(path)

    def load(self) -> UserPreferences:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return UserPreferences()
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return UserPreferences()
        if not isinstance(payload, dict):
            return UserPreferences()
        schema_version = payload.get("schema_version")
        enabled = payload.get("first_use_hints_enabled")
        seen = payload.get("seen_action_ids")
        if not isinstance(seen, list) or not all(isinstance(item, str) and item for item in seen):
            return UserPreferences()
        if schema_version == 1:
            return UserPreferences(False, frozenset(seen))
        if schema_version == 2 and isinstance(enabled, bool):
            return UserPreferences(enabled, frozenset(seen))
        if schema_version != 3 or not isinstance(enabled, bool):
            return UserPreferences()
        raw_speed = payload.get("speech_speed")
        if raw_speed is not None and raw_speed not in _SPEECH_SPEEDS:
            raw_speed = None
        speed = cast(SpeechSpeed, raw_speed) if isinstance(raw_speed, str) else None
        return UserPreferences(enabled, frozenset(seen), speed)

    def save(self, preferences: UserPreferences) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "schema_version": 3,
            "first_use_hints_enabled": preferences.first_use_hints_enabled,
            "seen_action_ids": sorted(preferences.seen_action_ids),
        }
        if preferences.speech_speed is not None:
            payload["speech_speed"] = preferences.speech_speed
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, self._path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
