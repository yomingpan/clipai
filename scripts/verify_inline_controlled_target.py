"""Verify controlled target read-back without inferring insertion from dispatch.

The input is JSONL from inline_dictation_controlled_target.py. A passing result
covers that target's text, Paste event, focus, and clipboard observations only;
it is not a complete ClipAI or microphone journey result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _clipboard_formats(record: dict) -> tuple[tuple[int, int, str], ...] | None:
    clipboard = record.get("clipboard", {})
    if clipboard.get("status") != "observed":
        return None
    try:
        return tuple(sorted(
            (int(item["id"]), int(item["bytes"]), str(item["sha256"]))
            for item in clipboard["formats"]
        ))
    except (KeyError, TypeError, ValueError):
        return None


def _literal_character_comparison(target: dict) -> dict[str, object]:
    reference = target.get("reference_codepoints")
    observed = target.get("observed_codepoints")
    errors = target.get("literal_character_errors")
    if not (
        type(reference) is int and 0 < reference <= 256
        and type(observed) is int and 0 <= observed <= 1024
        and type(errors) is int and 0 <= errors <= max(reference, observed)
    ):
        return {"status": "not_covered"}
    return {
        "status": "measured",
        "reference_codepoints": reference,
        "observed_codepoints": observed,
        "edit_distance": errors,
        "literal_character_error_rate": round(errors / reference, 3),
        "note": "Unicode codepoint comparison; punctuation and wording count, meaning is not assessed.",
    }


def verify(records: list[dict], *, scenario: str, text_policy: str = "exact") -> dict[str, object]:
    if scenario not in {"delivery", "cancel"}:
        raise ValueError("scenario must be delivery or cancel")
    if text_policy not in {"exact", "nonempty"} or (scenario == "cancel" and text_policy != "exact"):
        raise ValueError("text policy must be exact, or nonempty for delivery")
    checks: dict[str, str] = {}
    run_nonces = {record.get("run_nonce") for record in records}
    checks["single_run"] = "pass" if len(run_nonces) == 1 and None not in run_nonces else "fail"
    checks["no_command_errors"] = "pass" if not any(record.get("kind") == "command_error" for record in records) else "fail"
    timestamps = [record.get("monotonic_ns") for record in records if record.get("kind") != "command_error"]
    checks["ordered_observations"] = (
        "pass" if timestamps and all(isinstance(value, int) for value in timestamps)
        and timestamps == sorted(timestamps) else "fail"
    )
    starts = [record for record in records if record.get("kind") in {"ready", "reset"}]
    endings = [record for record in records if record.get("kind") == "observation"]
    if not starts or not endings:
        checks["complete_readback"] = "blocked"
        return _result(checks, scenario, next(iter(run_nonces)) if len(run_nonces) == 1 else None, text_policy)
    start, end = starts[-1], endings[-1]
    start_ns, end_ns = start.get("monotonic_ns"), end.get("monotonic_ns")
    valid_window = isinstance(start_ns, int) and isinstance(end_ns, int) and start_ns < end_ns
    checks["complete_readback"] = "pass" if valid_window else "fail"
    pastes = [
        record for record in records
        if record.get("kind") == "paste_observed" and valid_window
        and isinstance(record.get("monotonic_ns"), int)
        and start_ns < record["monotonic_ns"] <= end_ns
    ]
    checks["no_late_paste"] = (
        "pass" if valid_window and not any(
            record.get("kind") == "paste_observed"
            and isinstance(record.get("monotonic_ns"), int)
            and record["monotonic_ns"] > end_ns
            for record in records
        ) else "fail"
    )
    start_target, end_target = start.get("target", {}), end.get("target", {})
    start_clipboard, end_clipboard = _clipboard_formats(start), _clipboard_formats(end)
    checks["clipboard_observed"] = "pass" if start_clipboard is not None and end_clipboard is not None else "blocked"
    checks["clipboard_restored"] = (
        "pass" if start_clipboard == end_clipboard else "fail"
    ) if start_clipboard is not None and end_clipboard is not None else "blocked"
    expected_paste_count = 1 if scenario == "delivery" else 0
    checks["paste_count"] = (
        "pass" if len(pastes) == expected_paste_count
        and end_target.get("paste_count") == expected_paste_count else "fail"
    )
    if scenario == "delivery":
        text_matches_policy = (
            end_target.get("matches_expected") is True
            if text_policy == "exact"
            else start_target.get("utf8_bytes") == 0
            and isinstance(end_target.get("utf8_bytes"), int)
            and end_target["utf8_bytes"] > 0
            and end_target.get("sha256") != start_target.get("sha256")
        )
        checks["target_text"] = (
            "pass" if text_matches_policy
            and len(pastes) == 1
            and pastes[0].get("target", {}).get("sha256") == end_target.get("sha256") else "fail"
        )
        if len(pastes) == 1:
            paste_target = pastes[0].get("target", {})
            focused = paste_target.get("target_is_foreground")
            checks["paste_target_focus"] = (
                "pass" if focused is True
                else "blocked" if focused is None or paste_target.get("foreground_hwnd") == 0
                else "fail"
            )
        else:
            checks["paste_target_focus"] = "fail"
    else:
        checks["target_unchanged"] = (
            "pass" if end_target.get("sha256") == start_target.get("sha256")
            and end_target.get("utf8_bytes") == start_target.get("utf8_bytes") else "fail"
        )
    comparison = (
        _literal_character_comparison(end_target)
        if scenario == "delivery" and checks.get("target_text") == "pass"
        and checks.get("paste_count") == "pass"
        else {"status": "not_applicable"} if scenario == "cancel"
        else {"status": "not_covered"}
    )
    return _result(checks, scenario, next(iter(run_nonces)) if len(run_nonces) == 1 else None, text_policy, comparison)


def _result(
    checks: dict[str, str], scenario: str, run_nonce: object, text_policy: str,
    comparison: dict[str, object] | None = None,
) -> dict[str, object]:
    status = "fail" if "fail" in checks.values() else "blocked" if "blocked" in checks.values() else "pass"
    return {
        "schema_version": 1,
        "scope": "controlled_target_readback",
        "scenario": scenario,
        "text_policy": text_policy,
        "content_accuracy": "not_machine_verified" if text_policy == "nonempty" else "fixed_phrase_comparison",
        "literal_character_comparison": comparison or {"status": "not_covered"},
        "run_nonce": run_nonce,
        "status": status,
        "checks": checks,
        "note": "Paste Dispatch alone never proves target insertion; this result covers only the controlled target.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("--scenario", choices=("delivery", "cancel"), required=True)
    parser.add_argument("--text-policy", choices=("exact", "nonempty"), default="exact")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.events.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = verify(records, scenario=args.scenario, text_policy=args.text_policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
