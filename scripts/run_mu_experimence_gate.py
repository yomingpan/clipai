"""Run content-free Inline Dictation regression slices and append aggregate gates."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS: dict[str, tuple[str, ...]] = {
    "platform-stabilization": (
        "tests/platform/test_hotkey.py", "tests/platform/test_hotkey_edge_cases.py",
        "tests/platform/test_native_window.py",
        "tests/platform/test_keyboard_state.py",
    ),
    "core-contracts": ("tests/core/test_inline_dictation_placement_contract.py",),
    "services-placement": (
        "tests/services/test_user_preferences.py",
        "tests/platform/test_json_guidance_preferences.py",
    ),
    "app-coordination": (
        "tests/app/test_runtime.py", "tests/app/test_runtime_voice_input.py",
        "tests/app/test_runtime_user_preferences_voice.py",
        "tests/app/test_voice_capture_admission_policy.py",
        "tests/app/test_container.py",
    ),
    "ui-stabilization": (
        "tests/ui/test_result_dialog.py", "tests/ui/test_tray.py",
        "tests/ui/test_inline_dictation_window.py",
        "tests/ui/test_inline_dictation_owner.py", "tests/ui/test_owned_modals.py",
    ),
    "architecture-stabilization": ("tests/architecture",),
    "stt-webview": ("tests/platform/test_voice_webview_host.py",),
    "refine-service": ("tests/services/test_session_and_action.py",),
    "voice-controller-inline": ("tests/services/test_voice_input.py", "tests/services/test_voice_workflow_origin.py"),
    "voice-capture-timing": ("tests/app/test_voice_capture_timing.py", "tests/architecture/test_voice_deadline_ownership.py"),
    "refine-runtime": ("tests/app/test_inline_dictation.py",),
    "app-inline-paste": ("tests/app/test_runtime_voice_input.py", "tests/app/test_runtime.py"),
    "ui-inline": ("tests/ui/test_result_dialog.py",),
    "ime-and-architecture": ("tests/architecture",),
    "stt-config": ("tests/app/test_config.py", "tests/app/test_action_language_baseline.py"),
    "integration-smoke": ("tests/platform/test_application_instance.py::test_windows_instance_gate_releases_the_real_session_mutex",),
    "full-regression": ("tests",),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("steps", nargs="*", choices=tuple(STEPS))
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/mu-experimence-gate.jsonl")
    args = parser.parse_args()
    steps = args.steps or tuple(STEPS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for step in steps:
        marker = "integration" if step == "integration-smoke" else "not integration"
        command = [sys.executable, "scripts/run_unit_tests.py", "--", "-q", "-m", marker, *STEPS[step]]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        summary = re.search(r"(\d+) passed", result.stdout)
        cases = int(summary.group(1)) if summary else 0
        passed = result.returncode == 0 and cases > 0
        record = {
            "schema": 1,
            "gate": "mu-experimence",
            "step": step,
            "cases": cases,
            "passed": passed,
            "content_recorded": False,
            "device_evidence": False,
        }
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        print(f"{step}: {cases} passed, gate={passed}")
        if not passed:
            print((result.stdout + result.stderr)[-4000:], file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
