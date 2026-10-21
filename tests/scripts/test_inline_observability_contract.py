"""Literal wire/report contract; fixture timestamps are never device evidence."""

from scripts.report_inline_dictation_baseline import TRACE, summarize


def test_controlled_physical_right_alt_prompts_are_frozen():
    from scripts.run_inline_controlled_desktop import physical_shortcut_prompts
    assert physical_shortcut_prompts("raw") == ("單獨按一下實體右 Alt", "再單獨短按右 Alt，停止並貼上原文。")
    assert physical_shortcut_prompts("refine") == ("單獨按一下實體右 Alt", "按住右 Alt 約一秒（看到 ✦ 亮起）")


def test_inline_trace_wire_field_names_are_frozen() -> None:
    match = TRACE.fullmatch(
        "Inline trace monotonic_ns=1000000 stage=choice_shortcut "
        "interaction_id=i-1 capture_id=c-1 operation_id= mode=minimal outcome=long"
    )
    assert match is not None
    assert match.groupdict() == {
        "ns": "1000000", "stage": "choice_shortcut", "interaction": "i-1",
        "capture": "c-1", "operation": "", "mode": "minimal", "outcome": "long",
    }


def test_inline_report_schema_and_shortcut_stage_do_not_invent_delivery() -> None:
    report = summarize([
        "Inline trace monotonic_ns=1000000 stage=capture_requested "
        "interaction_id=i-1 capture_id=c-1 operation_id= mode=minimal outcome=short",
        "Inline trace monotonic_ns=2000000 stage=choice_shortcut "
        "interaction_id=i-1 capture_id=c-1 operation_id= mode= outcome=long",
        "Inline trace monotonic_ns=3000000 stage=stop_requested "
        "interaction_id=i-1 capture_id=c-1 operation_id= mode= outcome=long",
    ], cohort="golden-fixture", evidence="simulation")
    assert set(report) == {
        "schema_version", "created_at_utc", "device_cohort", "evidence",
        "observed_interactions", "malformed_inline_records", "groups",
        "insertion_truth", "ui_first_frame", "note",
    }
    assert report["evidence"] == "simulation"
    assert report["ui_first_frame"] == "not_observable_from_app_log"
    assert report["observed_interactions"] == 1
    group = report["groups"][0]
    assert set(group) == {
        "mode", "delivery_path", "interaction_count", "terminal_outcomes",
        "terminal_outcome_rates", "interaction_events", "incomplete_count",
        "invalid_count", "stage_latency",
    }
    assert group["delivery_path"] == "undelivered"
    assert group["terminal_outcomes"] == {"not_observable": 1}
    assert set(group["stage_latency"]) == {
        "first_press_to_listening", "stop_to_recognition", "refine_to_result",
        "paste_to_terminal", "first_press_to_terminal", "stop_to_terminal",
        "first_press_to_first_frame", "stop_to_dispatch",
    }


def test_frame_and_dispatch_intervals_require_their_own_observations() -> None:
    def line(ns, stage):
        return (
            f"Inline trace monotonic_ns={ns} stage={stage} interaction_id=i-1 "
            "capture_id= operation_id= mode=minimal outcome="
        )
    report = summarize([
        line(1_000_000, "capture_requested"), line(3_000_000, "first_frame_visible"),
        line(10_000_000, "stop_requested"), line(12_000_000, "recognition_settled"),
        line(13_000_000, "paste_requested"), line(15_000_000, "paste_dispatched"),
    ], cohort="golden-fixture", evidence="simulation")
    latency = report["groups"][0]["stage_latency"]
    assert latency["first_press_to_first_frame"]["median_ms"] == 2.0
    assert latency["stop_to_dispatch"]["median_ms"] == 5.0
    assert latency["stop_to_terminal"]["count"] == 0
    assert latency["stop_to_terminal"] == {
        "count": 0, "median_ms": None, "p90_ms": None, "p95_ms": None,
        "p99_ms": None, "max_ms": None,
        "cumulative_histogram": {
            "lte_50_ms": 0, "lte_100_ms": 0, "lte_250_ms": 0,
            "lte_500_ms": 0, "lte_1000_ms": 0, "gt_1000_ms": 0,
        },
    }
