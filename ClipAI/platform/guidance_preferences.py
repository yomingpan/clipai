from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from ClipAI.core.models import GuidancePreferences


class JsonGuidancePreferencesStore:
    def __init__(self, path: str | Path = "data/user_preferences.json") -> None:
        self._path = Path(path)

    def load(self) -> GuidancePreferences:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return GuidancePreferences()
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return GuidancePreferences()
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return GuidancePreferences()
        enabled = payload.get("first_use_hints_enabled")
        seen = payload.get("seen_action_ids")
        if not isinstance(enabled, bool) or not isinstance(seen, list) or not all(isinstance(item, str) and item for item in seen):
            return GuidancePreferences()
        return GuidancePreferences(enabled, frozenset(seen))

    def save(self, preferences: GuidancePreferences) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "first_use_hints_enabled": preferences.first_use_hints_enabled,
            "seen_action_ids": sorted(preferences.seen_action_ids),
        }
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
