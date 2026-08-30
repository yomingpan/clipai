from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from ClipAI.core.models import EntryActionRef


class JsonRecentActionStore:
    """Atomic, privacy-minimal persistence for recent replay references."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> tuple[EntryActionRef, ...]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ()
        if not isinstance(payload, list) or len(payload) > 3:
            return ()
        refs: list[EntryActionRef] = []
        for item in payload:
            if not isinstance(item, dict) or set(item) != {"action_id", "press_type"}:
                return ()
            action_id = item["action_id"]
            press_type = item["press_type"]
            if (
                not isinstance(action_id, str)
                or not action_id
                or press_type not in {"short", "long"}
            ):
                return ()
            refs.append(EntryActionRef(action_id, press_type))
        return tuple(refs)

    def save(self, refs: tuple[EntryActionRef, ...]) -> None:
        payload = [
            {"action_id": ref.action_id, "press_type": ref.press_type}
            for ref in refs[:3]
        ]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f".{self._path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
