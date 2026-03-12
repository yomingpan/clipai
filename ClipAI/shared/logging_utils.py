
import json
import os
import logging
from datetime import datetime, timezone

# Setup standard logging
logger = logging.getLogger("clipai")
logger.setLevel(logging.INFO)  # Default to INFO, hiding DEBUG logs

# Create console handler with a clean format
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('[clipai] %(levelname)s: %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

# Performance timing logger (child of clipai logger)
perf_logger = logging.getLogger("clipai.perf")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: dict, path: str = "logs/events.jsonl") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    event = dict(event)
    event["ts"] = _utc_now_iso()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")



