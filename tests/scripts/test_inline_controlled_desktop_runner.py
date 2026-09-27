import json
import sys
import threading
import pytest

from scripts import run_inline_controlled_desktop
from scripts.run_inline_controlled_desktop import assess


def test_attended_audio_replay_requires_existing_wav_and_delivery_scenario(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing.wav"
    monkeypatch.setattr(sys, "argv", [
        "controlled", "--mode", "minimal", "--scenario", "raw", "--freeform",
        "--audio-file", str(missing), "--output-dir", str(tmp_path / "run"),
    ])
    with pytest.raises(SystemExit) as absent:
        run_inline_controlled_desktop.main()
    assert absent.value.code == 2
    assert not (tmp_path / "run").exists()

    missing.write_bytes(b"RIFF")
    monkeypatch.setattr(sys, "argv", [
        "controlled", "--mode", "minimal", "--scenario", "cancel",
        "--audio-file", str(missing), "--output-dir", str(tmp_path / "run"),
    ])
    with pytest.raises(SystemExit) as cancel:
        run_inline_controlled_desktop.main()
    assert cancel.value.code == 2
    assert not (tmp_path / "run").exists()


def test_audio_replay_waits_for_the_matching_new_inline_listening_trace(tmp_path) -> None:
    log = tmp_path / "clipai.log"
    old = _trace(1, "capture_requested", mode="minimal") + "\n"
    log.write_text(old, encoding="utf-8")
    offset = log.stat().st_size
    log.write_text(old + _trace(2, "listening") + "\n", encoding="utf-8")
    assert not run_inline_controlled_desktop._wait_for_inline_listening(
        log, offset, threading.Event(), timeout=0.01,
    )

    mismatched = _trace(4, "listening").replace("interaction_id=inline-1", "interaction_id=inline-2")
    log.write_text(
        old + _trace(3, "capture_requested", mode="minimal") + "\n" + mismatched + "\n",
        encoding="utf-8",
    )
    assert not run_inline_controlled_desktop._wait_for_inline_listening(
        log, offset, threading.Event(), timeout=0.01,
    )

    log.write_text(
        old + _trace(3, "capture_requested", mode="minimal") + "\n"
        + _trace(4, "listening") + "\n",
        encoding="utf-8",
    )
    assert run_inline_controlled_desktop._wait_for_inline_listening(
        log, offset, threading.Event(), timeout=0.01,
    )

def _target(kind: str, ns: int, *, digest: str, pastes: int) -> dict:
    return {
        "kind": kind,
        "run_nonce": "run-1",
        "monotonic_ns": ns,
        "target": {
            "sha256": digest,
            "utf8_bytes": 0 if digest == "empty" else 4,
            "matches_expected": digest == "expected",
            "paste_count": pastes,
            "foreground_hwnd": 42,
            "target_hwnd": 42,
            "target_is_foreground": True,
        },
        "clipboard": {"status": "observed", "formats": [{"id": 13, "bytes": 8, "sha256": "original"}]},
    }


def _trace(ns: int, stage: str, *, mode: str = "", outcome: str = "") -> str:
    return (
        f"Inline trace monotonic_ns={ns} stage={stage} interaction_id=inline-1 "
        f"capture_id= operation_id= mode={mode} outcome={outcome}"
    )


def test_attended_delivery_requires_target_readback_and_matching_app_trace() -> None:
    records = [
        _target("ready", 1, digest="empty", pastes=0),
        _target("paste_observed", 2, digest="expected", pastes=1),
        _target("observation", 3, digest="expected", pastes=1),
    ]
    trace = [
        _trace(10, "capture_requested", mode="minimal"),
        _trace(11, "listening"),
        _trace(12, "stop_requested", outcome="short"),
        _trace(13, "recognition_settled"),
        _trace(14, "paste_requested"),
        _trace(15, "paste_terminal", outcome="dispatched_unconfirmed"),
    ]

    report = assess(records, trace, mode="minimal", scenario="raw")
    assert report["status"] == "pass"
    assert report["target"]["status"] == "pass"
    assert report["physical_hotkey"] == "operator_attested_not_independently_observed"
    assert report["device_baseline"] == "not_established_from_one_run"

    missing_app_receipt = assess(records, trace[:-1], mode="minimal", scenario="raw")
    assert missing_app_receipt["status"] == "blocked"
    assert missing_app_receipt["checks"]["app_terminal"] == "blocked"

    freeform_records = [dict(record, target=dict(record["target"])) for record in records]
    for record in freeform_records[1:]:
        record["target"]["matches_expected"] = False
    freeform = assess(freeform_records, trace, mode="minimal", scenario="raw", text_policy="nonempty")
    assert freeform["status"] == "pass"
    assert freeform["target"]["content_accuracy"] == "not_machine_verified"


def test_cancel_trace_with_late_paste_request_fails_even_if_target_is_unchanged() -> None:
    records = [
        _target("ready", 1, digest="empty", pastes=0),
        {**_target("escape_observed", 2, digest="empty", pastes=0), "key_modifier_state": 0},
        _target("observation", 3, digest="empty", pastes=0),
    ]
    trace = [
        _trace(10, "capture_requested", mode="minimal"),
        _trace(11, "discard_terminal", outcome="discarded"),
        _trace(12, "paste_requested"),
    ]

    report = assess(records, trace, mode="minimal", scenario="cancel")
    assert report["target"]["status"] == "pass"
    assert report["status"] == "fail"
    assert report["checks"]["app_terminal"] == "fail"
    assert report["escape_observation"] == {"target_keypress_count": 1, "modifier_states": [0]}


def test_cancel_requires_observed_escape_and_matching_discard_terminal() -> None:
    records = [
        _target("ready", 1, digest="empty", pastes=0),
        {**_target("escape_observed", 2, digest="empty", pastes=0), "key_modifier_state": 8},
        _target("observation", 3, digest="empty", pastes=0),
    ]
    trace = [
        _trace(10, "capture_requested", mode="minimal"),
        _trace(11, "listening"),
        _trace(12, "discard_requested"),
        _trace(13, "recognition_settled", outcome="empty_or_cancelled"),
        _trace(14, "discard_terminal", outcome="discarded"),
    ]

    report = assess(records, trace, mode="minimal", scenario="cancel")
    assert report["status"] == "pass"
    assert report["checks"]["escape_input"] == "pass"
    assert report["checks"]["app_terminal"] == "pass"

    missing_escape = assess([records[0], records[2]], trace, mode="minimal", scenario="cancel")
    assert missing_escape["status"] == "blocked"
    assert missing_escape["checks"]["escape_input"] == "blocked"

    failed_terminal = assess(records, trace[:-1] + [_trace(14, "discard_terminal", outcome="failed")],
                             mode="minimal", scenario="cancel")
    assert failed_terminal["status"] == "fail"
    assert failed_terminal["checks"]["app_terminal"] == "fail"

    missing_request = assess(records, trace[:2] + trace[3:], mode="minimal", scenario="cancel")
    assert missing_request["status"] == "fail"
    assert missing_request["checks"]["app_terminal"] == "fail"


def test_attended_run_rejects_invalid_app_trace_even_with_target_insertion() -> None:
    records = [
        _target("ready", 1, digest="empty", pastes=0),
        _target("paste_observed", 2, digest="expected", pastes=1),
        _target("observation", 3, digest="expected", pastes=1),
    ]
    trace = [
        _trace(10, "capture_requested", mode="minimal"),
        _trace(11, "listening"),
        _trace(12, "stop_requested"),
        _trace(13, "paste_requested"),
        _trace(14, "paste_terminal", outcome="dispatched_unconfirmed"),
    ]

    report = assess(records, trace, mode="minimal", scenario="raw")
    assert report["target"]["status"] == "pass"
    assert report["app_trace"]["groups"][0]["invalid_count"] == 1
    assert report["checks"]["app_trace_validity"] == "fail"
    assert report["status"] == "fail"

    malformed = assess(records, trace + ["Inline trace malformed"], mode="minimal", scenario="raw")
    assert malformed["app_trace"]["malformed_inline_records"] == 1
    assert malformed["checks"]["app_trace_validity"] == "fail"


def test_minimal_refine_requires_long_stop_gesture() -> None:
    records = [
        _target("ready", 1, digest="empty", pastes=0),
        _target("paste_observed", 2, digest="expected", pastes=1),
        _target("observation", 3, digest="expected", pastes=1),
    ]
    trace = [
        _trace(10, "capture_requested", mode="minimal"),
        _trace(11, "listening"),
        _trace(12, "stop_requested", outcome="short"),
        _trace(13, "recognition_settled"),
        _trace(14, "refine_requested"),
        _trace(15, "refine_settled", outcome="completed"),
        _trace(16, "paste_requested"),
        _trace(17, "paste_terminal", outcome="dispatched_unconfirmed"),
    ]

    report = assess(records, trace, mode="minimal", scenario="refine")
    assert report["target"]["status"] == "pass"
    assert report["checks"]["delivery_path"] == "pass"
    assert report["checks"]["stop_gesture"] == "fail"
    assert report["status"] == "fail"


def test_choice_delivery_requires_ready_choice_before_output() -> None:
    records = [
        _target("ready", 1, digest="empty", pastes=0),
        _target("paste_observed", 2, digest="expected", pastes=1),
        _target("observation", 3, digest="expected", pastes=1),
    ]
    trace = [
        _trace(10, "capture_requested", mode="choice"),
        _trace(11, "listening"),
        _trace(12, "stop_requested", outcome="short"),
        _trace(13, "recognition_settled"),
        _trace(14, "refine_requested"),
        _trace(15, "refine_settled", outcome="completed"),
        _trace(16, "paste_requested"),
        _trace(17, "paste_terminal", outcome="dispatched_unconfirmed"),
    ]

    report = assess(records, trace, mode="choice", scenario="refine")
    assert report["target"]["status"] == "pass"
    assert report["checks"]["choice_ready"] == "fail"
    assert report["status"] == "fail"


def test_attended_run_preserves_existing_evidence_directory(monkeypatch, tmp_path, capsys) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    report = output_dir / "report.json"
    report.write_text("original report", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["controlled", "--mode", "minimal", "--scenario", "cancel", "--output-dir", str(output_dir)]
    )
    monkeypatch.setattr(run_inline_controlled_desktop, "harness_is_elevated",
                        lambda: (_ for _ in ()).throw(AssertionError("preflight ran")))

    assert run_inline_controlled_desktop.main() == 2
    assert report.read_text(encoding="utf-8") == "original report"
    assert "輸出目錄" in capsys.readouterr().err


def test_attended_run_stops_before_opening_target_when_app_is_absent(
    monkeypatch, tmp_path, capsys
) -> None:
    output_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys, "argv", ["controlled", "--mode", "minimal", "--scenario", "cancel", "--output-dir", str(output_dir)]
    )
    monkeypatch.setattr(run_inline_controlled_desktop, "app_instance_is_running", lambda: False)
    monkeypatch.setattr(
        run_inline_controlled_desktop.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("target opened")),
    )

    assert run_inline_controlled_desktop.main() == 2
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert report["checks"]["app_instance"] == "blocked"
    assert "ClipAI" in capsys.readouterr().err


def test_attended_run_rejects_elevated_shell_before_opening_target(
    monkeypatch, tmp_path, capsys
) -> None:
    output_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys, "argv", ["controlled", "--mode", "minimal", "--scenario", "cancel", "--output-dir", str(output_dir)]
    )
    monkeypatch.setattr(run_inline_controlled_desktop, "harness_is_elevated", lambda: True)
    monkeypatch.setattr(
        run_inline_controlled_desktop.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("target opened")),
    )

    assert run_inline_controlled_desktop.main() == 2
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["reason_code"] == "controlled_harness_elevated"
    assert report["checks"]["desktop_privilege"] == "blocked"
    assert "管理員" in capsys.readouterr().err


def test_attended_run_rejects_mode_mismatch_before_opening_target(
    monkeypatch, tmp_path
) -> None:
    output_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys, "argv", ["controlled", "--mode", "minimal", "--scenario", "cancel", "--output-dir", str(output_dir)]
    )
    monkeypatch.setattr(run_inline_controlled_desktop, "harness_is_elevated", lambda: False)
    monkeypatch.setattr(run_inline_controlled_desktop, "app_instance_is_running", lambda: True)
    monkeypatch.setattr(run_inline_controlled_desktop, "configured_inline_mode", lambda: "choice")
    monkeypatch.setattr(
        run_inline_controlled_desktop.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("target opened")),
    )

    assert run_inline_controlled_desktop.main() == 2
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["reason_code"] == "inline_mode_mismatch"
    assert report["checks"]["configured_mode"] == "blocked"
