import json
import os
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: dict, path: str = "logs/events.jsonl") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    event = dict(event)
    event["ts"] = _utc_now_iso()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
