import pytest

from scripts.compare_inline_dictation_baselines import compare


def report(cohort: str, median: float, *, evidence: str = "controlled_desktop") -> dict:
    return {
        "evidence": evidence,
        "device_cohort": cohort,
        "groups": [{
            "mode": "minimal", "delivery_path": "raw", "invalid_count": 0,
            "interaction_count": 25,
            "terminal_outcomes": {"dispatched_unconfirmed": 25},
            "stage_latency": {"stop_to_terminal": {"count": 25, "median_ms": median, "p95_ms": median + 20}},
        }],
    }


def test_same_condition_comparison_keeps_counts_and_latency_deltas() -> None:
    result = compare(report("machine-a", 100), report("machine-a", 85))
    group = result["groups"][0]

    assert group["status"] == "comparable"
    assert group["stage_deltas"]["stop_to_terminal"]["median_delta_ms"] == -15
    assert group["stage_deltas"]["stop_to_terminal"]["p95_delta_ms"] == -15
    assert group["stage_deltas"]["stop_to_terminal"]["p99_delta_ms"] is None
    assert result["insertion_truth"] == "requires_external_observer"


def test_comparison_refuses_virtual_time_and_different_devices() -> None:
    with pytest.raises(ValueError, match="controlled desktop"):
        compare(report("machine-a", 100, evidence="simulation"), report("machine-a", 85))
    with pytest.raises(ValueError, match="same condition"):
        compare(report("machine-a", 100), report("machine-b", 85))


def test_comparison_marks_incomplete_trace_as_not_comparable() -> None:
    before = report("machine-a", 100)
    before["groups"][0]["incomplete_count"] = 1

    assert compare(before, report("machine-a", 85))["groups"][0]["status"] == "not_comparable"


def test_comparison_includes_p99_only_when_both_reports_support_it() -> None:
    before, after = report("machine-a", 100), report("machine-a", 85)
    before["groups"][0]["stage_latency"]["stop_to_terminal"]["p99_ms"] = 140
    after["groups"][0]["stage_latency"]["stop_to_terminal"]["p99_ms"] = 120

    assert compare(before, after)["groups"][0]["stage_deltas"]["stop_to_terminal"]["p99_delta_ms"] == -20
