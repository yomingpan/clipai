"""Deterministic selection-policy gate; emits content-free JSONL metrics."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
import statistics
import time

from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.selection_capture import SelectionCaptureCoordinator


@dataclass(frozen=True)
class _Snapshot:
    text: str


class _Clipboard:
    def __init__(self) -> None:
        self.value = "frozen clipboard"
        self.sequence = 1

    def read_text(self): return self.value
    def write_text(self, text): self.value = text; self.sequence += 1
    def write_transient_text(self, text): self.write_text(text)
    def snapshot(self): return _Snapshot(self.value)
    def sequence_number(self): return self.sequence
    def restore_if_unchanged(self, snapshot, expected_sequence):
        if self.sequence != expected_sequence:
            return False
        self.write_text(snapshot.text)
        return True


class _Adapter:
    def __init__(self, clipboard, *, copy: bool, held: bool = False):
        self.clipboard, self.copy, self.held = clipboard, copy, held

    def modifier_is_pressed(self, modifier): return self.held and modifier == "ctrl"
    def copy_selection(self):
        if self.copy:
            self.clipboard.write_text("verified selection")


class _Probe:
    def __init__(self, outcome, *, current=True):
        self.outcome, self.current = outcome, current
        self.source = SelectionSource(ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")

    def capture_source(self, target=None): return self.source
    def source_is_current(self, source): return self.current and source == self.source
    def probe(self, source, cancellation): return self.outcome


_SCENARIOS = (
    ("uia-selected", SelectionCaptureOutcome("verified selection", "selected", strategy="uia"), True, False, ("selected", "")),
    ("uia-caret", SelectionCaptureOutcome(status="none", reason="uia_caret_only", strategy="uia"), False, False, ("none", "uia_caret_only")),
    ("verified-copy", SelectionCaptureOutcome(reason="selection_only_copy_available", copy_selection_only=True), True, False, ("selected", "")),
    ("verified-copy-timeout", SelectionCaptureOutcome(reason="selection_only_copy_available", copy_selection_only=True), False, False, ("unknown", "copy_timeout")),
    ("unsupported", SelectionCaptureOutcome(reason="uia_unsupported", strategy="uia"), False, False, ("unknown", "uia_unsupported")),
    ("wrong-source", SelectionCaptureOutcome("wrong", "selected", strategy="uia"), False, False, ("unknown", "source_changed")),
    ("modifier-timeout", SelectionCaptureOutcome("wrong", "selected", strategy="uia"), False, True, ("unknown", "modifier_timeout")),
    ("cancelled", SelectionCaptureOutcome("wrong", "selected", strategy="uia"), False, False, ("cancelled", "")),
)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))]


def run(seed: int, cases: int = 480) -> dict[str, object]:
    rng = random.Random(seed)
    samples = [rng.choice(_SCENARIOS) for _ in range(cases - len(_SCENARIOS))] + list(_SCENARIOS)
    rng.shuffle(samples)
    correct = exact_expected = exact_available = 0
    latencies = []
    for name, probe_outcome, copy, held, expected in samples:
        clipboard = _Clipboard()
        probe = _Probe(probe_outcome, current=name != "wrong-source")
        token = CancellationToken()
        if name == "cancelled":
            token.cancel()
        coordinator = SelectionCaptureCoordinator(
            ClipboardTransactionCoordinator(clipboard),
            _Adapter(clipboard, copy=copy, held=held),
            probe,
            modifier_release_timeout_sec=0,
            timeout_sec=0.001,
            poll_sec=0,
        )
        started = time.perf_counter()
        outcome = coordinator.capture(token)
        latencies.append((time.perf_counter() - started) * 1000)
        correct += (outcome.status, outcome.reason) == expected
        if expected[0] == "selected":
            exact_expected += 1
            exact_available += outcome.text == "verified selection"
        if clipboard.value != "frozen clipboard":
            correct -= 1
    return {
        "schema": 1,
        "gate": "selection-policy-simulation",
        "seed": seed,
        "cases": cases,
        "policy_correct": correct,
        "policy_correct_rate": correct / cases,
        "exact_expected": exact_expected,
        "exact_available": exact_available,
        "exact_available_rate": exact_available / exact_expected if exact_expected else 1.0,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 3),
            "p90": round(_percentile(latencies, .90), 3),
            "p95": round(_percentile(latencies, .95), 3),
        },
        "content_recorded": False,
        "device_evidence": False,
        "passed": correct == cases and exact_available == exact_expected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/selection-reliability.jsonl"))
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
