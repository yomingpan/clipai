
"""
Diagnostic timing instrumentation for popup latency analysis.

Usage:
    from clipai.diag_timing import diag

    diag.mark("hotkey_triggered", action_id="smart_qa")
    ...
    diag.mark("semaphore_acquired")
    ...
    diag.mark("first_token_rendered")

Each mark prints a timestamped log line relative to the first mark
in the current trace (T+0ms). A new trace starts whenever
diag.start() or the first mark after a reset is called.

Controlled by config.yaml ``logging.perf_timing`` (takes precedence)
or the ``CLIPAI_DIAG_TIMING`` env-var (backward-compatible fallback).
"""

import os
import threading
from time import perf_counter

from clipai.logging_utils import perf_logger

_PREFIX = "[⏱ diag]"


def _resolve_enabled() -> bool:
    """Determine if perf timing is enabled (called once at module load)."""
    # Config.yaml takes precedence
    try:
        import yaml
        with open("config/config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        perf_setting = config.get("logging", {}).get("perf_timing")
        if perf_setting is not None:
            return bool(perf_setting)
    except Exception:
        pass
    # Fall back to env var (backward compatible)
    return os.environ.get("CLIPAI_DIAG_TIMING", "1") != "0"


_ENABLED = _resolve_enabled()

# When perf timing is enabled, explicitly set perf_logger to DEBUG level.
# Without this, perf_logger inherits INFO from the parent "clipai" logger,
# which silently drops all debug() calls.
if _ENABLED:
    import logging as _logging
    perf_logger.setLevel(_logging.DEBUG)


class _DiagTiming:
    """Per-thread timing trace."""

    def __init__(self):
        self._lock = threading.Lock()
        # Per-thread origin so concurrent dispatches don't collide
        self._origins: dict[int, float] = {}
        self._labels: dict[int, str] = {}  # optional action_id per thread

    def start(self, action_id: str = ""):
        """Begin a new timing trace for the current thread."""
        if not _ENABLED:
            return
        tid = threading.get_ident()
        now = perf_counter()
        with self._lock:
            self._origins[tid] = now
            self._labels[tid] = action_id
        self._emit(0.0, "trace_start", action_id=action_id)

    def mark(self, checkpoint: str, **extra):
        """Record a timing checkpoint. Auto-starts if no trace is active."""
        if not _ENABLED:
            return
        tid = threading.get_ident()
        now = perf_counter()
        with self._lock:
            origin = self._origins.get(tid)
            if origin is None:
                # Auto-start
                self._origins[tid] = now
                origin = now
            action_id = self._labels.get(tid, "")
        delta_ms = (now - origin) * 1000
        self._emit(delta_ms, checkpoint, action_id=action_id, **extra)

    def end(self, checkpoint: str = "trace_end"):
        """End the current trace and clean up."""
        if not _ENABLED:
            return
        tid = threading.get_ident()
        now = perf_counter()
        with self._lock:
            origin = self._origins.pop(tid, None)
            action_id = self._labels.pop(tid, "")
        if origin is not None:
            delta_ms = (now - origin) * 1000
            self._emit(delta_ms, checkpoint, action_id=action_id, total=True)

    def get_origin(self) -> float | None:
        """Get the origin timestamp for the current thread (for cross-thread transfer)."""
        tid = threading.get_ident()
        with self._lock:
            return self._origins.get(tid)

    def get_label(self) -> str:
        """Get the action_id label for the current thread."""
        tid = threading.get_ident()
        with self._lock:
            return self._labels.get(tid, "")

    def set_origin(self, origin: float, action_id: str = ""):
        """Set the origin for the current thread (for cross-thread transfer)."""
        if not _ENABLED:
            return
        tid = threading.get_ident()
        with self._lock:
            self._origins[tid] = origin
            self._labels[tid] = action_id

    def _emit(self, delta_ms: float, checkpoint: str, action_id: str = "",
              total: bool = False, **extra):
        parts = [_PREFIX]
        if action_id:
            parts.append(f"[{action_id}]")
        tag = "TOTAL" if total else f"T+{delta_ms:>7.1f}ms"
        parts.append(f"{tag} {checkpoint}")
        if extra:
            kv = " ".join(f"{k}={v}" for k, v in extra.items())
            parts.append(f"({kv})")
        perf_logger.debug(" ".join(parts))


# Module-level singleton
diag = _DiagTiming()



