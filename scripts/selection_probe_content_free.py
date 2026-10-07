"""Probe the current Windows selection and emit structural facts only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from ClipAI.platform.selection_uia import WindowsSelectionProbe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/selection-probe.jsonl"))
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    probe = WindowsSelectionProbe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("a", encoding="utf-8") as stream:
            for attempt in range(args.attempts):
                source = probe.capture_source(None)
                started = time.perf_counter()
                outcome = probe.probe(source, None) if source is not None else None
                elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                identity = (
                    hashlib.sha256(
                        f"{source.window.window_token}:{source.window.process_id}".encode("ascii")
                    ).hexdigest()[:16]
                    if source is not None else None
                )
                record = {
                    "schema": 1,
                    "gate": "selection-live-probe",
                    "attempt": attempt + 1,
                    "source_identity_hash": identity,
                    "status": outcome.status if outcome is not None else "unavailable",
                    "reason": outcome.reason if outcome is not None else "source_unavailable",
                    "strategy": outcome.strategy if outcome is not None else "",
                    "selection_detected": outcome.selection_detected if outcome is not None else False,
                    "copy_selection_only": outcome.copy_selection_only if outcome is not None else False,
                    "focus_restored": outcome.focus_restored if outcome is not None else False,
                    "elapsed_ms": elapsed_ms,
                    "content_recorded": False,
                    "executable_path_recorded": False,
                }
                stream.write(json.dumps(record, ensure_ascii=True) + "\n")
                stream.flush()
    finally:
        probe.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
