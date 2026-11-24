from __future__ import annotations

import json

from scripts.report_inline_dictation_baseline import summarize


def event(ns: int, stage: str, interaction: str, *, mode: str = "", outcome: str = "") -> str:
    return (
        f"Inline trace monotonic_ns={ns} stage={stage} interaction_id={interaction} "
        f"capture_id=capture-secret operation_id=operation-secret mode={mode} outcome={outcome}"
    )


def test_stage_report_separates_modes_and_delivery_paths_without_content() -> None:
    lines = [
        event(1_000_000, "capture_requested", "inline-private-1", mode="choice"),
        event(2_000_000, "listening", "inline-private-1"),
        event(5_000_000, "stop_requested", "inline-private-1"),
        event(7_000_000, "recognition_settled", "inline-private-1"),
        event(9_000_000, "paste_requested", "inline-private-1"),
        event(12_000_000, "paste_terminal", "inline-private-1", outcome="dispatched_unconfirmed"),
        event(20_000_000, "capture_requested", "inline-private-2", mode="minimal"),
        event(23_000_000, "stop_requested", "inline-private-2"),
        event(24_000_000, "recognition_settled", "inline-private-2"),
        event(25_000_000, "refine_requested", "inline-private-2"),
        event(30_000_000, "refine_settled", "inline-private-2", outcome="completed"),
        event(31_000_000, "paste_requested", "inline-private-2"),
        event(36_000_000, "paste_terminal", "inline-private-2", outcome="failed"),
        "private dictated words and clipboard payload",
    ]
    report = summarize(lines, cohort="controlled-test", evidence="simulation")
    groups = {(group["mode"], group["delivery_path"]): group for group in report["groups"]}

    assert report["observed_interactions"] == 2
    assert groups[("choice", "raw")]["stage_latency"]["stop_to_terminal"]["median_ms"] == 7.0
    assert groups[("minimal", "refine")]["stage_latency"]["refine_to_result"]["median_ms"] == 5.0
    assert groups[("choice", "raw")]["terminal_outcomes"] == {"dispatched_unconfirmed": 1}
    assert groups[("minimal", "refine")]["terminal_outcomes"] == {"failed": 1}
    encoded = json.dumps(report)
    assert "private dictated words" not in encoded
    assert "inline-private" not in encoded
    assert "capture-secret" not in encoded
    assert "operation-secret" not in encoded


def test_refinement_timeout_is_counted_without_inventing_paste_success() -> None:
    report = summarize([
        event(1_000_000, "capture_requested", "inline-timeout", mode="minimal"),
        event(2_000_000, "stop_requested", "inline-timeout", outcome="long"),
        event(3_000_000, "recognition_settled", "inline-timeout", outcome="content_available"),
        event(4_000_000, "refine_requested", "inline-timeout"),
        event(9_000_000, "refine_settled", "inline-timeout", outcome="timed_out"),
        event(10_000_000, "recovery_visible_requested", "inline-timeout"),
    ], cohort="controlled-test", evidence="simulation")
    group = report["groups"][0]

    assert group["interaction_events"]["refine_timed_out"] == 1
    assert group["terminal_outcomes"] == {"not_observable": 1}
    assert group["stage_latency"]["refine_to_result"]["median_ms"] == 5.0


def test_incomplete_and_malformed_trace_do_not_invent_latency_or_success() -> None:
    report = summarize([
        event(10, "capture_requested", "inline-3", mode="minimal"),
        "Inline trace malformed with private text",
    ], cohort="controlled-test", evidence="component")
    group = report["groups"][0]

    assert report["malformed_inline_records"] == 1
    assert group["terminal_outcomes"] == {"not_observable": 1}
    assert group["incomplete_count"] == 1
    assert group["stage_latency"]["first_press_to_terminal"]["median_ms"] is None


def test_trace_oracle_rejects_terminal_without_paste_admission() -> None:
    report = summarize([
        event(1_000_000, "capture_requested", "inline-mutated", mode="choice"),
        event(2_000_000, "paste_terminal", "inline-mutated", outcome="dispatched_unconfirmed"),
    ], cohort="controlled-test", evidence="simulation")
    group = report["groups"][0]

    assert group["invalid_count"] == 1
    assert group["terminal_outcomes"] == {"invalid_trace": 1}
    assert group["stage_latency"]["first_press_to_terminal"]["count"] == 0


def test_equal_timestamp_stages_keep_log_order() -> None:
    report = summarize([
        event(1_000_000, "capture_requested", "inline-tied", mode="minimal"),
        event(2_000_000, "listening", "inline-tied"),
        event(3_000_000, "stop_requested", "inline-tied"),
        event(4_000_000, "recognition_settled", "inline-tied"),
        event(4_000_000, "paste_requested", "inline-tied"),
        event(5_000_000, "paste_terminal", "inline-tied", outcome="dispatched_unconfirmed"),
    ], cohort="controlled-test", evidence="simulation")

    group = report["groups"][0]
    assert group["invalid_count"] == 0
    assert group["terminal_outcomes"] == {"dispatched_unconfirmed": 1}
    assert group["stage_latency"]["paste_to_terminal"]["median_ms"] == 1.0


def test_discard_and_copy_recovery_are_counted_without_claiming_insertion() -> None:
    report = summarize([
        event(1_000_000, "capture_requested", "inline-recovery", mode="minimal"),
        event(2_000_000, "stop_requested", "inline-recovery"),
        event(3_000_000, "recognition_settled", "inline-recovery"),
        event(4_000_000, "recovery_visible_requested", "inline-recovery"),
        event(5_000_000, "copy_result", "inline-recovery", outcome="succeeded"),
        event(6_000_000, "discard_terminal", "inline-recovery", outcome="discarded"),
        event(7_000_000, "capture_requested", "inline-empty", mode="minimal"),
        event(8_000_000, "discard_terminal", "inline-empty", outcome="failed"),
    ], cohort="controlled-test", evidence="simulation")
    group = report["groups"][0]

    assert group["terminal_outcomes"] == {"discarded": 1, "failed": 1}
    assert group["terminal_outcome_rates"] == {"discarded": 0.5, "failed": 0.5}
    assert group["interaction_events"] == {
        "copy_succeeded": 1,
        "discarded": 2,
        "recovery_requested": 1,
    }
    assert group["stage_latency"]["first_press_to_terminal"]["count"] == 0
    assert report["insertion_truth"] == "not_observable_from_app_log"


def test_tail_percentiles_require_enough_samples_and_keep_distribution() -> None:
    lines = []
    for index in range(100):
        interaction = f"inline-{index}"
        start = index * 2_000_000_000
        lines.extend((
            event(start, "capture_requested", interaction, mode="choice"),
            event(start + (index + 1) * 1_000_000, "listening", interaction),
            event(start + 1_500_000_000, "discard_terminal", interaction, outcome="discarded"),
        ))
    distribution = summarize(lines, cohort="controlled-test", evidence="simulation")["groups"][0]["stage_latency"]["first_press_to_listening"]

    assert distribution["count"] == 100
    assert distribution["p99_ms"] == 99.0
    assert distribution["cumulative_histogram"]["lte_50_ms"] == 50
    assert distribution["cumulative_histogram"]["lte_100_ms"] == 100


def test_trace_oracle_rejects_paste_after_discard() -> None:
    report = summarize([
        event(1_000_000, "capture_requested", "inline-discarded", mode="minimal"),
        event(2_000_000, "recognition_settled", "inline-discarded"),
        event(3_000_000, "discard_terminal", "inline-discarded", outcome="discarded"),
        event(4_000_000, "paste_requested", "inline-discarded"),
        event(5_000_000, "paste_terminal", "inline-discarded", outcome="dispatched_unconfirmed"),
    ], cohort="controlled-test", evidence="simulation")

    assert report["groups"][0]["invalid_count"] == 1
    assert report["groups"][0]["terminal_outcomes"] == {"invalid_trace": 1}
