"""Deterministic foreground-activation gate; emits content-free JSONL metrics."""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import random
import statistics
import time

from ClipAI.platform.window_activation import activate_top_level_window
from ClipAI.support.statistics import percentile


class _Kernel32:
    def GetCurrentThreadId(self) -> int:
        return 1


class _User32:
    def __init__(self, foreground_thread: int, target_thread: int, timeout: int) -> None:
        self.foreground = 30
        self.foreground_thread = foreground_thread
        self.target_thread = target_thread
        self.timeout = timeout
        self.attached: list[tuple[int, int, bool]] = []

    def SystemParametersInfoW(self, action, _param, value, _flags):
        if action == 0x2000:
            ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32))[0] = self.timeout
        else:
            self.timeout = int(value.value or 0)
        return True

    def GetForegroundWindow(self): return self.foreground
    def GetWindowThreadProcessId(self, hwnd, _pid): return self.foreground_thread if hwnd == 30 else self.target_thread
    def AttachThreadInput(self, current, related, attached): self.attached.append((current, related, bool(attached))); return True
    def BringWindowToTop(self, _hwnd): return True
    def SetForegroundWindow(self, hwnd):
        if self.timeout:
            return False
        self.foreground = hwnd
        return True
    def SetActiveWindow(self, _hwnd): return 0


def run(seed: int, cases: int = 480) -> dict[str, object]:
    rng = random.Random(seed)
    acquired = restored = detached = 0
    latencies: list[float] = []
    user32 = _User32(2, 3, 1)
    for _ in range(cases):
        original = rng.randint(1, 500_000)
        user32.foreground = 30
        user32.foreground_thread = rng.randint(2, 7)
        user32.target_thread = rng.randint(2, 7)
        user32.timeout = original
        user32.attached.clear()
        started = time.perf_counter()
        acquired += activate_top_level_window(42, user32=user32, kernel32=_Kernel32())
        latencies.append((time.perf_counter() - started) * 1000)
        restored += user32.timeout == original
        attached = [item for item in user32.attached if item[2]]
        released = [item for item in user32.attached if not item[2]]
        detached += released == [(a, b, False) for a, b, _ in reversed(attached)]
    p95 = percentile(latencies, .95)
    passed = acquired == restored == detached == cases and p95 <= 0.05
    return {
        "schema": 1,
        "gate": "voice-focus-simulation",
        "seed": seed,
        "cases": cases,
        "focus_acquired": acquired,
        "focus_acquired_rate": acquired / cases,
        "lock_timeout_restored": restored,
        "input_queues_detached": detached,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 3),
            "p95": round(p95, 3),
        },
        "content_recorded": False,
        "device_evidence": False,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/voice-focus-reliability.jsonl"))
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 41, 73])
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = [run(seed) for seed in args.seeds]
    with args.output.open("w", encoding="utf-8") as stream:
        for result in results:
            stream.write(json.dumps(result, ensure_ascii=True) + "\n")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
