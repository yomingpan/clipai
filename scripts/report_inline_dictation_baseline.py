"""Summarize content-free Inline Dictation log stages from one device run.

This reports dispatch acknowledgement, never confirmed insertion. Supply only
logs from a controlled desktop run when making a device baseline claim.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics


TRACE = re.compile(
    r"Inline trace monotonic_ns=(?P<ns>\d+) stage=(?P<stage>\S+) "
    r"interaction_id=(?P<interaction>\S*) capture_id=(?P<capture>\S*) "
    r"operation_id=(?P<operation>\S*) mode=(?P<mode>\S*) outcome=(?P<outcome>\S*)"
)
INTERVALS = {
    "first_press_to_listening": ("capture_requested", "listening"),
    "stop_to_recognition": ("stop_requested", "recognition_settled"),
    "refine_to_result": ("refine_requested", "refine_settled"),
    "paste_to_terminal": ("paste_requested", "paste_terminal"),
    "first_press_to_terminal": ("capture_requested", "paste_terminal"),
    "stop_to_terminal": ("stop_requested", "paste_terminal"),
}
HISTOGRAM_BOUNDARIES_MS = (50, 100, 250, 500, 1000)
REQUIRED_PREDECESSOR = {
    "listening": "capture_requested",
    "stop_requested": "capture_requested",
    "refine_requested": "recognition_settled",
    "refine_settled": "refine_requested",
    "paste_requested": "recognition_settled",
    "paste_terminal": "paste_requested",
    "discard_terminal": "capture_requested",
    "copy_result": "capture_requested",
}
UNIQUE_STAGES = frozenset({"capture_requested", "listening", "stop_requested", "recognition_settled", "refine_requested", "refine_settled", "paste_requested", "paste_terminal", "discard_terminal"})


def _percentile(values: list[float], percentile: int) -> float:
    ordered = sorted(values)
    index = max(0, (percentile * len(ordered) + 99) // 100 - 1)
    return round(ordered[index], 1)


def _distribution(values: list[float]) -> dict[str, object]:
    histogram = {
        **{f"lte_{boundary}_ms": sum(value <= boundary for value in values) for boundary in HISTOGRAM_BOUNDARIES_MS},
        "gt_1000_ms": sum(value > HISTOGRAM_BOUNDARIES_MS[-1] for value in values),
    }
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 1) if values else None,
        "p90_ms": _percentile(values, 90) if len(values) >= 10 else None,
        "p95_ms": _percentile(values, 95) if len(values) >= 20 else None,
        "p99_ms": _percentile(values, 99) if len(values) >= 100 else None,
        "max_ms": round(max(values), 1) if values else None,
        "cumulative_histogram": histogram,
    }


def summarize(lines: list[str], *, cohort: str, evidence: str) -> dict[str, object]:
    interactions: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
    malformed = 0
    for line in lines:
        if "Inline trace " not in line:
            continue
        match = TRACE.search(line)
        if match is None or not match["interaction"]:
            malformed += 1
            continue
        interactions[match["interaction"]].append((
            int(match["ns"]), match["stage"], match["mode"], match["outcome"],
        ))

    groups: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"outcomes": Counter(), "interaction_events": Counter(), "durations": defaultdict(list), "incomplete": 0, "invalid": 0}
    )
    for events in interactions.values():
        # Preserve log order when the clock reports the same nanosecond for
        # consecutive lifecycle stages; tuple sorting would reorder by name.
        events.sort(key=lambda event: event[0])
        stages: dict[str, int] = {}
        mode = "unknown"
        outcome = "not_observable"
        invalid = False
        interaction_events: Counter[str] = Counter()
        for timestamp, stage, observed_mode, observed_outcome in events:
            if stage in UNIQUE_STAGES and stage in stages:
                invalid = True
            prerequisite = REQUIRED_PREDECESSOR.get(stage)
            if prerequisite is not None and prerequisite not in stages:
                invalid = True
            stages.setdefault(stage, timestamp)
            if stage == "capture_requested" and observed_mode in {"choice", "minimal"}:
                mode = observed_mode
            if stage == "paste_terminal":
                outcome = observed_outcome
            elif stage == "discard_terminal" and outcome == "not_observable":
                outcome = observed_outcome
            if stage == "recovery_visible_requested":
                interaction_events["recovery_requested"] += 1
            elif stage == "refine_settled" and observed_outcome in {"completed", "failed", "timed_out", "unavailable", "cancelled"}:
                interaction_events[f"refine_{observed_outcome}"] += 1
            elif stage == "copy_result":
                interaction_events[f"copy_{observed_outcome}"] += 1
            elif stage == "discard_terminal":
                interaction_events["discarded"] += 1
        path = "refine" if "refine_requested" in stages else "raw" if "paste_requested" in stages else "undelivered"
        group = groups[(mode, path)]
        group["interaction_events"].update(interaction_events)
        if "capture_requested" not in stages or mode == "unknown":
            invalid = True
        if "discard_terminal" in stages and "paste_requested" in stages and stages["paste_requested"] > stages["discard_terminal"]:
            invalid = True
        if invalid:
            outcome = "invalid_trace"
            group["invalid"] += 1
        group["outcomes"][outcome] += 1
        if outcome == "not_observable":
            group["incomplete"] += 1
        if invalid:
            continue
        for label, (start, end) in INTERVALS.items():
            if start in stages and end in stages and stages[end] >= stages[start]:
                group["durations"][label].append((stages[end] - stages[start]) / 1_000_000)

    summaries = []
    for (mode, path), group in sorted(groups.items()):
        summaries.append({
            "mode": mode,
            "delivery_path": path,
            "interaction_count": sum(group["outcomes"].values()),
            "terminal_outcomes": dict(sorted(group["outcomes"].items())),
            "terminal_outcome_rates": {
                outcome: round(count / sum(group["outcomes"].values()), 4)
                for outcome, count in sorted(group["outcomes"].items())
            },
            "interaction_events": dict(sorted(group["interaction_events"].items())),
            "incomplete_count": group["incomplete"],
            "invalid_count": group["invalid"],
            "stage_latency": {key: _distribution(group["durations"].get(key, [])) for key in INTERVALS},
        })
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "device_cohort": cohort,
        "evidence": evidence,
        "observed_interactions": len(interactions),
        "malformed_inline_records": malformed,
        "groups": summaries,
        "insertion_truth": "not_observable_from_app_log",
        "ui_first_frame": "not_observable_from_app_log",
        "note": "Terminal dispatched_unconfirmed means a Paste shortcut was sent, not that text was inserted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--device-cohort", required=True)
    parser.add_argument("--evidence", choices=("controlled_desktop", "component", "simulation"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.log.read_text(encoding="utf-8", errors="replace").splitlines(),
                       cohort=args.device_cohort, evidence=args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
