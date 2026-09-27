import json
from pathlib import Path
import subprocess

import pytest

from scripts.run_inline_dictation_validation import reassess_attended_report, requested_layers_pass, run_layer


@pytest.fixture(autouse=True)
def isolated_local_app_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))


def test_requested_desktop_layer_must_pass_even_when_fast_layer_passes() -> None:
    layers = {"fast": {"status": "pass"}, "tk": {"status": "pass"}, "webview": {"status": "blocked"}}

    assert requested_layers_pass(layers, tk=False, webview=False)
    assert requested_layers_pass(layers, tk=True, webview=False)
    assert not requested_layers_pass(layers, tk=True, webview=True)


def test_webview_initialization_timeout_remains_a_failed_test(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        report = next(item.removeprefix("--junitxml=") for item in command if item.startswith("--junitxml="))
        Path(report).write_text(
            '<testsuite tests="1" failures="1" errors="0" skipped="0">'
            '<testcase name="host"><failure message="test_loaded timeout" /></testcase>'
            '</testsuite>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr("scripts.run_inline_dictation_validation.subprocess.run", fake_run)
    layer = run_layer("webview", ("test_host.py",), tmp_path, integration=True, webview=True)

    assert layer["status"] == "fail"
    assert layer["reason_code"] == "webview_initialization_timeout"
    assert layer["failed"] == 1


def test_webview2_startup_error_is_distinct_from_bridge_timeout(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        report = next(item.removeprefix("--junitxml=") for item in command if item.startswith("--junitxml="))
        Path(report).write_text(
            '<testsuite tests="1" failures="1" errors="0" skipped="0">'
            '<testcase name="host"><failure message="test_loaded timeout">'
            'WebView2 initialization failed with exception: E_UNEXPECTED'
            '</failure></testcase></testsuite>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr("scripts.run_inline_dictation_validation.subprocess.run", fake_run)
    layer = run_layer("webview", ("test_host.py",), tmp_path, integration=True, webview=True)

    assert layer["status"] == "fail"
    assert layer["reason_code"] == "webview2_initialization_failed"


def test_skipped_required_desktop_case_blocks_the_layer(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        report = next(item.removeprefix("--junitxml=") for item in command if item.startswith("--junitxml="))
        Path(report).write_text(
            '<testsuite tests="2" failures="0" errors="0" skipped="1">'
            '<testcase name="window" /><testcase name="native_focus"><skipped message="no foreground" /></testcase>'
            '</testsuite>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.run_inline_dictation_validation.subprocess.run", fake_run)
    layer = run_layer("tk", ("test_window.py",), tmp_path, integration=True)

    assert layer["status"] == "blocked"
    assert layer["reason_code"] == "required_desktop_case_skipped"
    assert layer["passed"] == 1
    assert layer["skipped"] == 1


def test_desktop_layer_uses_local_app_data_for_webview_profile(tmp_path: Path, monkeypatch) -> None:
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        report = next(item.removeprefix("--junitxml=") for item in command if item.startswith("--junitxml="))
        Path(report).write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="host" /></testsuite>', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.run_inline_dictation_validation.subprocess.run", fake_run)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    layer = run_layer("webview", ("test_host.py",), evidence, integration=True, webview=True)

    basetemp = Path(next(item.removeprefix("--basetemp=") for item in commands[0] if item.startswith("--basetemp=")))
    assert layer["status"] == "pass"
    assert basetemp.is_relative_to(tmp_path / "local-app-data" / "ClipAI" / "InlineValidation")
    assert not basetemp.is_relative_to(tmp_path / "evidence")


def test_attended_manifest_rechecks_raw_evidence_instead_of_old_verdict(tmp_path: Path) -> None:
    run = tmp_path / "attended-run"
    run.mkdir()
    report = run / "report.json"
    report.write_text(json.dumps({
        "status": "fail", "mode_requested": "minimal", "scenario_requested": "raw",
        "target": {"text_policy": "exact"}, "run_nonce": "run-1",
    }), encoding="utf-8")

    def target(kind: str, ns: int, *, digest: str, pastes: int) -> dict:
        return {
            "kind": kind, "run_nonce": "run-1", "monotonic_ns": ns,
            "target": {
                "sha256": digest, "utf8_bytes": 0 if digest == "empty" else 4,
                "matches_expected": digest == "expected", "paste_count": pastes,
                "foreground_hwnd": 42, "target_hwnd": 42, "target_is_foreground": True,
            },
            "clipboard": {"status": "observed", "formats": [{"id": 13, "bytes": 8, "sha256": "original"}]},
        }

    records = [target("ready", 1, digest="empty", pastes=0),
               target("paste_observed", 2, digest="expected", pastes=1),
               target("observation", 3, digest="expected", pastes=1)]
    (run / "target.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    def trace(stage: str, ns: int, *, mode: str = "", outcome: str = "") -> str:
        return (f"Inline trace monotonic_ns={ns} stage={stage} interaction_id=inline-1 "
                f"capture_id= operation_id= mode={mode} outcome={outcome}")

    lines = [trace("capture_requested", 10, mode="minimal"), trace("listening", 11),
             trace("stop_requested", 12, outcome="short"), trace("recognition_settled", 13),
             trace("paste_requested", 14), trace("paste_terminal", 15, outcome="dispatched_unconfirmed")]
    (run / "inline-trace.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    reassessed = reassess_attended_report(report)
    assert reassessed["status"] == "pass"
    assert reassessed["checks"]["stop_gesture"] == "pass"

    lines[2] = trace("stop_requested", 12, outcome="long")
    (run / "inline-trace.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    reassessed = reassess_attended_report(report)
    assert reassessed["status"] == "fail"
    assert reassessed["checks"]["stop_gesture"] == "fail"

    lines[2] = trace("stop_requested", 12, outcome="short")
    (run / "inline-trace.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    old_report = json.loads(report.read_text(encoding="utf-8"))
    old_report["run_nonce"] = "another-run"
    report.write_text(json.dumps(old_report), encoding="utf-8")
    assert reassess_attended_report(report)["status"] == "fail"

    (run / "inline-trace.log").unlink()
    assert reassess_attended_report(report)["status"] == "blocked"
