from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


class JsonlArchiveStore:
    def __init__(self, path: str | Path = "data/archive.jsonl") -> None:
        self._path = Path(path)

    def save(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        record = {"created_at": datetime.now(timezone.utc).isoformat(), "text": text}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

