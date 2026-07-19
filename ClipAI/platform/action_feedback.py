from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import threading

from ClipAI.core.models import ActionFeedbackRecord


class JsonlActionFeedbackStore:
    def __init__(self, path: str | Path = "data/action_feedback.jsonl") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: ActionFeedbackRecord) -> None:
        payload = json.dumps(asdict(record), ensure_ascii=False)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
