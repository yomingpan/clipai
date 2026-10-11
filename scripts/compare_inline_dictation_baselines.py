"""Compare two controlled desktop Inline Dictation reports by matching cohort.

The comparison remains descriptive; target insertion and UI frame evidence must
come from the external observer before it can support a release decision.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def compare(before: dict, after: dict) -> dict:
    if before.get("evidence") != "controlled_desktop" or after.get("evidence") != "controlled_desktop":
        raise ValueError("Both reports must come from controlled desktop runs.")
    if before.get("device_cohort") != after.get("device_cohort"):
        raise ValueError("Device cohorts differ; compare the same condition.")
    old_groups = {(group["mode"], group["delivery_path"]): group for group in before.get("groups", [])}
    new_groups = {(group["mode"], group["delivery_path"]): group for group in after.get("groups", [])}
    results = []
    for mode, path in sorted(old_groups.keys() | new_groups.keys()):
        old = old_groups.get((mode, path))
        new = new_groups.get((mode, path))
        if old is None or new is None:
            results.append({"mode": mode, "delivery_path": path, "status": "not_comparable", "reason": "group_missing"})
            continue
        intervals = {}
        for stage in old.get("stage_latency", {}).keys() | new.get("stage_latency", {}).keys():
            prior = old.get("stage_latency", {}).get(stage, {})
            current = new.get("stage_latency", {}).get(stage, {})
            median_before, median_after = prior.get("median_ms"), current.get("median_ms")
            p95_before, p95_after = prior.get("p95_ms"), current.get("p95_ms")
            p99_before, p99_after = prior.get("p99_ms"), current.get("p99_ms")
            intervals[stage] = {
                "before_count": prior.get("count", 0),
                "after_count": current.get("count", 0),
                "median_delta_ms": round(median_after - median_before, 1) if median_before is not None and median_after is not None else None,
                "p95_delta_ms": round(p95_after - p95_before, 1) if p95_before is not None and p95_after is not None else None,
                "p99_delta_ms": round(p99_after - p99_before, 1) if p99_before is not None and p99_after is not None else None,
            }
        results.append({
            "mode": mode,
            "delivery_path": path,
            "status": "comparable" if old.get("invalid_count", 0) == new.get("invalid_count", 0) == old.get("incomplete_count", 0) == new.get("incomplete_count", 0) == 0 else "not_comparable",
            "before_interactions": old["interaction_count"],
            "after_interactions": new["interaction_count"],
            "before_terminal_outcomes": old["terminal_outcomes"],
            "after_terminal_outcomes": new["terminal_outcomes"],
            "stage_deltas": intervals,
        })
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "device_cohort": before["device_cohort"],
        "groups": results,
        "insertion_truth": "requires_external_observer",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.before.read_text(encoding="utf-8")), json.loads(args.after.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0 if all(group["status"] == "comparable" for group in result["groups"]) and result["groups"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
