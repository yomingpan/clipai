"""Run the fixed Inline Dictation evidence layers and write a safe manifest.

The fast runner uses virtual time. Its duration is never a device baseline.
Pass --tk and --webview only on an isolated interactive Windows desktop.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from uuid import uuid4
from xml.etree import ElementTree


FAST_CASES = (
    "tests/journeys/test_inline_dictation_journeys.py",
    "tests/services/test_voice_input.py",
    "tests/services/test_paste_operation.py",
    "tests/services/test_clipboard_transaction.py",
    "tests/app/test_runtime_voice_input.py",
    "tests/app/test_runtime.py",
    "tests/scripts/test_inline_trace_report.py",
    "tests/scripts/test_inline_baseline_comparison.py",
    "tests/scripts/test_inline_controlled_target.py",
    "tests/scripts/test_inline_controlled_target_verifier.py",
    "tests/scripts/test_inline_controlled_desktop_runner.py",
    "tests/scripts/test_inline_validation_runner.py",
    "tests/architecture",
)
TK_CASES = ("tests/ui/test_inline_dictation_window.py", "tests/scripts/test_inline_controlled_target.py")
WEBVIEW_CASES = ("tests/platform/test_voice_webview_host_integration.py",)


def source_revision() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    changes = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {
        "commit": revision.stdout.strip() if revision.returncode == 0 else "unavailable",
        "tracked_worktree_dirty": bool(changes.stdout.strip()) if changes.returncode == 0 else None,
    }


def run_layer(name: str, cases: tuple[str, ...], output_dir: Path, *, integration: bool = False, webview: bool = False) -> dict[str, object]:
    report = output_dir / f"{name}.xml"
    # WebView2 needs its browser profile under LocalAppData on the interactive
    # desktop. Tk tests do not use a browser profile and keep temporary files
    # beside the evidence so restricted LocalAppData does not block them.
    if webview:
        local_data = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        desktop_root = local_data / "ClipAI" / "InlineValidation"
        desktop_root.mkdir(parents=True, exist_ok=True)
        basetemp = desktop_root / f"{name}-{uuid4().hex[:8]}"
    else:
        basetemp = output_dir / (name + "-tmp")
    command = [
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "-m", "integration" if integration else "not integration",
        *cases,
        f"--basetemp={basetemp}",
        f"--junitxml={report}",
        "--tb=short",
    ]
    environment = os.environ.copy()
    if webview:
        environment["CLIPAI_RUN_VOICE_WEBVIEW_INTEGRATION"] = "1"
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment, check=False)
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    webview_initialization_timeout = False
    webview2_initialization_failed = False
    tcl_initialization_failed = False
    if report.exists():
        root = ElementTree.parse(report).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is not None:
            counts = {key: int(suite.attrib.get(key, 0)) for key in counts}
            failures = [node for case in suite.iter("testcase") for node in case if node.tag in {"failure", "error"}]
            webview_initialization_timeout = bool(failures) and all("test_loaded" in (node.attrib.get("message", "") + (node.text or "")) for node in failures)
            webview2_initialization_failed = any(
                "WebView2 initialization failed" in (node.attrib.get("message", "") + (node.text or ""))
                for node in failures
            )
            tcl_initialization_failed = bool(failures) and all(
                "_tkinter.TclError" in (node.attrib.get("message", "") + (node.text or ""))
                for node in failures
            )
    passed = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    status = (
        "blocked" if integration and tcl_initialization_failed
        else "blocked" if integration and completed.returncode == 0 and counts["skipped"] > 0
        else "pass" if completed.returncode == 0 and passed > 0
        else "fail"
    )
    return {
        "status": status,
        "reason_code": (
            "tcl_initialization_failed" if tcl_initialization_failed and status == "blocked"
            else "required_desktop_case_skipped" if status == "blocked"
            else "webview2_initialization_failed" if webview and webview2_initialization_failed
            else "webview_initialization_timeout" if webview and webview_initialization_timeout
            else ""
        ),
        "evidence": "desktop_component" if integration else "deterministic_simulation",
        "tests": counts["tests"],
        "passed": passed,
        "failed": counts["failures"] + counts["errors"],
        "skipped": counts["skipped"],
        "exit_code": completed.returncode,
        "junit": report.name,
    }


def requested_layers_pass(layers: dict[str, dict[str, object]], *, tk: bool, webview: bool) -> bool:
    requested = ["fast"]
    if tk:
        requested.append("tk")
    if webview:
        requested.append("webview")
    return all(layers[name]["status"] == "pass" for name in requested)


def reassess_attended_report(report_path: Path) -> dict[str, object]:
    """Recheck a saved desktop run from raw observations, not its old verdict."""
    artifact = report_path.parent.name
    try:
        original = json.loads(report_path.read_text(encoding="utf-8"))
        mode = original["mode_requested"]
        scenario = original["scenario_requested"]
        text_policy = original["target"]["text_policy"]
        if mode not in {"choice", "minimal"} or scenario not in {"raw", "refine", "cancel"}:
            raise ValueError("unsupported attended scenario")
        if text_policy not in {"exact", "nonempty"}:
            raise ValueError("unsupported text policy")
        records = [
            json.loads(line) for line in (report_path.parent / "target.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        trace_lines = (report_path.parent / "inline-trace.log").read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError, KeyError, TypeError):
        return {"artifact": artifact, "status": "blocked", "reason_code": "attended_evidence_unavailable"}

    if __package__:
        from .run_inline_controlled_desktop import assess
    else:
        from run_inline_controlled_desktop import assess
    result = assess(records, trace_lines, mode=mode, scenario=scenario, text_policy=text_policy)
    status = result["status"]
    if original.get("run_nonce") != result["target"].get("run_nonce"):
        status = "fail"
    audio_replay = original.get("audio_replay")
    replay_reported = (
        isinstance(audio_replay, dict)
        and audio_replay.get("source") == "fixed_wav_speaker_playback"
        and audio_replay.get("playback_returned") is True
        and isinstance(audio_replay.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", audio_replay["sha256"]) is not None
    )
    return {
        "artifact": artifact,
        "status": status,
        "mode": mode,
        "scenario": scenario,
        "checks": result["checks"],
        "evidence": "attended_controlled_target_and_app_trace",
        "physical_hotkey": result["physical_hotkey"],
        "microphone_audio_source": (
            "speaker_replay_reported_input_not_independently_confirmed"
            if replay_reported else result["microphone_audio_source"]
        ),
        "audio_replay_sha256": audio_replay["sha256"] if replay_reported else None,
        "content_accuracy": result["target"]["content_accuracy"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tk", action="store_true", help="run Tk window checks on an interactive desktop")
    parser.add_argument("--webview", action="store_true", help="run the real WebView2 host checks")
    parser.add_argument("--attended-report", type=Path, action="append", default=[],
                        help="include and recheck a saved controlled desktop report; repeat for each run")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/inline-dictation-validation"))
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    layers = {"fast": run_layer("fast", FAST_CASES, output_dir)}
    layers["tk"] = run_layer("tk", TK_CASES, output_dir, integration=True) if args.tk else {"status": "not_covered"}
    layers["webview"] = run_layer("webview", WEBVIEW_CASES, output_dir, integration=True, webview=True) if args.webview else {"status": "not_covered"}
    layers["controlled_paste_target"] = {
        "status": "not_covered",
        "scope": "automated_multi_target_matrix",
    }
    if args.attended_report:
        runs = [reassess_attended_report(path.resolve()) for path in args.attended_report]
        attended_status = (
            "fail" if any(run["status"] == "fail" for run in runs)
            else "blocked" if any(run["status"] == "blocked" for run in runs)
            else "pass"
        )
        layers["attended_smoke"] = {"status": attended_status, "runs": runs}
    layers["physical_hotkey_and_loopback_audio"] = {"status": "not_covered"}
    layers["device_latency_baseline"] = (
        {"status": "blocked", "reason_code": "voice_chain_unavailable"}
        if args.webview and layers["webview"]["status"] != "pass"
        else {"status": "not_covered"}
    )
    manifest = {
        "schema_version": 1,
        "scenario_version": "adr-0019-fixed-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source_revision(),
        "os": {"system": platform.system(), "release": platform.release()},
        "python_version": sys.version.split()[0],
        "layers": layers,
        "latency_note": "Virtual-clock and pytest durations are not device latency baselines.",
    }
    destination = output_dir / "manifest.json"
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(destination)
    selected_pass = requested_layers_pass(layers, tk=args.tk, webview=args.webview)
    if args.attended_report:
        selected_pass = selected_pass and layers["attended_smoke"]["status"] == "pass"
    return 0 if selected_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
