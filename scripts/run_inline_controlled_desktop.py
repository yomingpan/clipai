"""Guide one attended Inline Dictation run against a read-back Tk target.

Run from an unlocked Windows desktop with this worktree's ClipAI already open.
Only a fixed, consented test phrase should be passed as --expected-text. The
artifacts contain hashes and allowlisted lifecycle stages, never target text.
"""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from ClipAI.app.application_lifecycle import build_application_instance_gate

if __package__:
    from .report_inline_dictation_baseline import TRACE, summarize
    from .verify_inline_controlled_target import verify
else:
    from report_inline_dictation_baseline import TRACE, summarize
    from verify_inline_controlled_target import verify


ROOT = Path(__file__).resolve().parents[1]


def app_instance_is_running() -> bool:
    """Check the app's existing single-instance gate before asking for HID input."""
    lease = build_application_instance_gate().acquire()
    if lease is None:
        return True
    lease.close()
    return False


def harness_is_elevated() -> bool:
    """An elevated target cannot represent normal-privilege ClipAI input."""
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def configured_inline_mode() -> str | None:
    """Read the source worktree's persisted mode before an attended run."""
    try:
        payload = json.loads((ROOT / "data" / "user_preferences.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mode = payload.get("inline_input_mode") if isinstance(payload, dict) else None
    return mode if mode in {"choice", "minimal"} else None


def _matching_fixture_phrase(audio_file: Path) -> str:
    """Use only a phrase tied to the exact WAV bytes by its local manifest."""
    try:
        manifest = json.loads((audio_file.parent / "manifest.json").read_text(encoding="utf-8-sig"))
        digest = hashlib.sha256(audio_file.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("fixtures"), list):
        return ""
    for fixture in manifest["fixtures"]:
        if not isinstance(fixture, dict):
            continue
        phrase = fixture.get("phrase")
        if (
            fixture.get("file") == audio_file.name
            and fixture.get("sha256") == digest
            and isinstance(phrase, str)
            and 0 < len(phrase) <= 256
        ):
            return phrase
    return ""


def _write_blocked_report(
    path: Path, *, mode: str, scenario: str, run_nonce: str,
    reason_code: str, check_name: str = "app_instance",
) -> None:
    report = {
        "schema_version": 1,
        "scope": "attended_controlled_target_preflight",
        "status": "blocked",
        "mode_requested": mode,
        "scenario_requested": scenario,
        "checks": {check_name: "blocked"},
        "reason_code": reason_code,
        "run_nonce": run_nonce,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _wait_record(path: Path, kind: str, *, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for record in reversed(_records(path)):
            if record.get("kind") == kind:
                return record
        time.sleep(0.05)
    raise TimeoutError(f"controlled target did not report {kind}")


def _command(process: subprocess.Popen[str], name: str) -> None:
    if process.stdin is None:
        raise RuntimeError("controlled target input is unavailable")
    process.stdin.write(json.dumps({"command": name}) + "\n")
    process.stdin.flush()


def _wait_for_inline_listening(
    log_path: Path, start_offset: int, stop: threading.Event, *, timeout: float = 30.0,
) -> bool:
    """Observe the new interaction's Listening acknowledgement without changing focus."""
    deadline = time.monotonic() + timeout
    while not stop.is_set() and time.monotonic() < deadline:
        try:
            with log_path.open("rb") as source:
                source.seek(start_offset)
                lines = source.read().decode("utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        current_interaction = ""
        for line in lines:
            match = TRACE.search(line)
            if match is None:
                continue
            if match["stage"] == "capture_requested":
                current_interaction = match["interaction"]
            if (
                current_interaction
                and match["stage"] == "listening"
                and match["interaction"] == current_interaction
            ):
                return True
        stop.wait(0.1)
    return False


def _audio_playback_within_capture(
    trace_lines: list[str], interval_ns: tuple[int, int],
) -> bool:
    """Require the whole speaker playback inside one observed capture interval."""
    start_ns, end_ns = interval_ns
    if start_ns <= 0 or end_ns <= start_ns:
        return False
    events = [match for line in trace_lines if (match := TRACE.search(line)) is not None]
    interactions = {match["interaction"] for match in events if match["interaction"]}
    if len(interactions) != 1:
        return False
    listening = [int(match["ns"]) for match in events if match["stage"] == "listening"]
    stops = [int(match["ns"]) for match in events if match["stage"] == "stop_requested"]
    return len(listening) == len(stops) == 1 and listening[0] <= start_ns < end_ns <= stops[0]


def assess(
    records: list[dict], trace_lines: list[str], *, mode: str, scenario: str,
    text_policy: str = "exact", audio_playback_interval_ns: tuple[int, int] | None = None,
) -> dict[str, object]:
    target_scenario = "cancel" if scenario == "cancel" else "delivery"
    target_result = verify(records, scenario=target_scenario, text_policy=text_policy)
    parsed = [match for line in trace_lines if (match := TRACE.search(line)) is not None]
    interactions = {match["interaction"] for match in parsed if match["interaction"]}
    app_trace = summarize(trace_lines, cohort="single_attended_run", evidence="controlled_desktop")
    checks: dict[str, str] = {"target_readback": target_result["status"]}
    if audio_playback_interval_ns is not None:
        checks["audio_replay_during_capture"] = (
            "pass" if _audio_playback_within_capture(trace_lines, audio_playback_interval_ns)
            else "fail"
        )
    if scenario == "cancel":
        checks["escape_input"] = (
            "pass" if any(record.get("kind") == "escape_observed" for record in records)
            else "blocked"
        )
    checks["app_trace_validity"] = (
        "fail" if app_trace["malformed_inline_records"]
        or any(group["invalid_count"] for group in app_trace["groups"])
        else "blocked" if not interactions else "pass"
    )
    if len(interactions) != 1:
        checks["single_app_interaction"] = "blocked" if not interactions else "fail"
    else:
        checks["single_app_interaction"] = "pass"
        events = [match for match in parsed if match["interaction"] in interactions]
        starts = [match for match in events if match["stage"] == "capture_requested"]
        checks["frozen_mode"] = (
            "pass" if len(starts) == 1 and starts[0]["mode"] == mode else "fail"
        )
        stages = [match["stage"] for match in events]
        if scenario == "cancel":
            discard_requests = [index for index, stage in enumerate(stages) if stage == "discard_requested"]
            discard_terminals = [
                (index, match) for index, match in enumerate(events)
                if match["stage"] == "discard_terminal"
            ]
            checks["app_terminal"] = (
                "fail" if "paste_requested" in stages or "paste_terminal" in stages
                else "fail" if discard_terminals and (
                    len(discard_requests) != 1 or len(discard_terminals) != 1
                    or discard_requests[0] >= discard_terminals[0][0]
                    or discard_terminals[0][1]["outcome"] != "discarded"
                )
                else "pass" if discard_terminals else "blocked"
            )
        else:
            terminals = [match for match in events if match["stage"] == "paste_terminal"]
            checks["app_terminal"] = (
                "pass" if len(terminals) == 1 and terminals[0]["outcome"] == "dispatched_unconfirmed"
                else "fail" if terminals else "blocked"
            )
            checks["delivery_path"] = (
                "pass" if ("refine_requested" in stages) == (scenario == "refine") else "fail"
            )
            if mode == "choice":
                recognition = [index for index, stage in enumerate(stages) if stage == "recognition_settled"]
                choices = [index for index, stage in enumerate(stages) if stage == "choice_ready"]
                output_intents = [
                    index for index, stage in enumerate(stages)
                    if stage in {"refine_requested", "paste_requested"}
                ]
                checks["choice_ready"] = (
                    "pass" if len(recognition) == len(choices) == 1 and output_intents
                    and recognition[0] < choices[0] < min(output_intents) else "fail"
                )
            if mode == "minimal":
                stops = [match for match in events if match["stage"] == "stop_requested"]
                expected_gesture = "long" if scenario == "refine" else "short"
                checks["stop_gesture"] = (
                    "pass" if len(stops) == 1 and stops[0]["outcome"] == expected_gesture else "fail"
                )
    status = "fail" if "fail" in checks.values() else "blocked" if "blocked" in checks.values() else "pass"
    return {
        "schema_version": 1,
        "scope": "attended_controlled_target_and_app_trace",
        "status": status,
        "mode_requested": mode,
        "scenario_requested": scenario,
        "checks": checks,
        "target": target_result,
        "app_trace": app_trace,
        "escape_observation": {
            "target_keypress_count": sum(record.get("kind") == "escape_observed" for record in records),
            "modifier_states": sorted({
                record["key_modifier_state"] for record in records
                if record.get("kind") == "escape_observed"
                and isinstance(record.get("key_modifier_state"), int)
            }),
        },
        "physical_hotkey": "operator_attested_not_independently_observed",
        "microphone_audio_source": "operator_supplied_not_recorded",
        "literal_character_comparison": (
            target_result["literal_character_comparison"]
            if scenario == "raw" else {"status": "not_applicable"}
        ),
        "ui_first_frame": "not_observed",
        "device_baseline": "not_established_from_one_run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("choice", "minimal"), required=True)
    parser.add_argument("--scenario", choices=("raw", "refine", "cancel"), required=True)
    parser.add_argument("--expected-text", default="", help="fixed test phrase; with --freeform, report literal character error without gating delivery")
    parser.add_argument("--freeform", action="store_true", help="check nonempty stable insertion; optional --expected-text measures literal character error")
    parser.add_argument("--audio-file", type=Path, help="fixed WAV to play through speakers after capture starts")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--late-wait", type=float, default=3.0)
    args = parser.parse_args()
    if args.freeform and args.scenario == "cancel":
        parser.error("--freeform is only valid for raw and refine")
    if args.audio_file and args.scenario == "cancel":
        parser.error("--audio-file is only valid for raw and refine")
    audio_file = args.audio_file.resolve() if args.audio_file else None
    if audio_file is not None and (not audio_file.is_file() or audio_file.suffix.lower() != ".wav"):
        parser.error("--audio-file must point to an existing WAV file")
    if args.scenario != "cancel" and not args.freeform and not args.expected_text:
        parser.error("--expected-text is required for raw and refine")
    if args.late_wait < 1:
        parser.error("--late-wait must be at least one second")
    reference_text = args.expected_text
    fixture_reference = False
    if audio_file is not None and args.freeform and args.scenario == "raw" and not reference_text:
        reference_text = _matching_fixture_phrase(audio_file)
        fixture_reference = bool(reference_text)
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(
        (output_dir / name).exists() for name in ("target.jsonl", "inline-trace.log", "report.json")
    ):
        print("輸出目錄已有受控測試證據；請為重試指定新的 --output-dir。", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "target.jsonl"
    trace_path = output_dir / "inline-trace.log"
    report_path = output_dir / "report.json"
    run_nonce = uuid4().hex
    if harness_is_elevated():
        _write_blocked_report(report_path, mode=args.mode, scenario=args.scenario,
                              run_nonce=run_nonce, reason_code="controlled_harness_elevated",
                              check_name="desktop_privilege")
        print("受控測試不可從系統管理員 PowerShell 執行。請開啟一般權限的 PowerShell，讓文字框與 ClipAI 使用相同權限。", file=sys.stderr)
        print(report_path)
        return 2
    if not app_instance_is_running():
        _write_blocked_report(report_path, mode=args.mode, scenario=args.scenario,
                              run_nonce=run_nonce, reason_code="clipai_app_not_running")
        print(
            "ClipAI 尚未在這個 Windows session 執行。請從另一個可見的 PowerShell 視窗啟動這份工作樹的 main.py，並保持它執行。",
            file=sys.stderr,
        )
        print(report_path)
        return 2
    saved_mode = configured_inline_mode()
    if saved_mode != args.mode:
        _write_blocked_report(report_path, mode=args.mode, scenario=args.scenario,
                              run_nonce=run_nonce,
                              reason_code="inline_mode_mismatch" if saved_mode else "inline_mode_unavailable",
                              check_name="configured_mode")
        print(f"Inline 模式不符：工作樹設定為 {saved_mode or '未知'}，命令指定 {args.mode}。請從 ClipAI Tray 選好模式後重試。", file=sys.stderr)
        print(report_path)
        return 2
    app_log = ROOT / "logs" / "clipai.log"
    log_offset = app_log.stat().st_size if app_log.exists() else 0
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "inline_dictation_controlled_target.py"),
         "--output", str(events_path), "--expected-text", reference_text,
         "--run-nonce", run_nonce],
        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    playback_stop = threading.Event()
    playback_thread: threading.Thread | None = None
    playback_result: list[str] = []
    playback_interval_ns: list[int] = []
    try:
        _wait_record(events_path, "ready")
        print("受控文字框已開啟。請確認這個工作樹的 ClipAI 正在執行，並已從 Tray 選好模式。")
        print("本輪只做一次聽寫互動；完成後不要再次啟動聽寫或修改文字框／剪貼簿。")
        print("按 Enter 後，請點選受控文字框，再以實體 Ctrl+Alt+M 開始聽寫。")
        spoken_prompt = "播放固定測試音檔" if audio_file else "說一段話" if args.freeform else "說出固定測試文字"
        if args.scenario == "cancel":
            print("請在錄音期間按 Esc 取消；不要手動貼上。")
        elif args.scenario == "raw":
            print(f"{spoken_prompt}後，以第二次短按停止；完整選擇模式還需明確選擇原文。")
        else:
            if args.mode == "minimal":
                print(f"{spoken_prompt}後，第二次按住 Ctrl+Alt+M，讓 M 鍵本身保持按下約一秒，再放開並等待潤稿終態。")
            else:
                print(f"{spoken_prompt}後，以第二次短按停止，再於選擇視窗點選潤飾。")
        input("準備好時按 Enter：")
        if not app_instance_is_running():
            _write_blocked_report(report_path, mode=args.mode, scenario=args.scenario,
                                  run_nonce=run_nonce, reason_code="clipai_app_exited_before_hotkey")
            print("ClipAI 已在按快捷鍵前結束；請保持這份工作樹的 main.py 執行。", file=sys.stderr)
            print(report_path)
            return 2
        _command(process, "focus")
        _wait_record(events_path, "focus_requested")
        if audio_file is not None:
            import winsound

            def replay_after_listening() -> None:
                if not _wait_for_inline_listening(app_log, log_offset, playback_stop):
                    playback_result.append("listening_not_observed")
                    return
                if playback_stop.is_set():
                    playback_result.append("audio_playback_cancelled")
                    return
                try:
                    playback_interval_ns.append(time.monotonic_ns())
                    winsound.PlaySound(str(audio_file), winsound.SND_FILENAME)
                    playback_interval_ns.append(time.monotonic_ns())
                except RuntimeError:
                    playback_result.append("audio_playback_unavailable")
                    return
                playback_result.append("played")

            playback_thread = threading.Thread(target=replay_after_listening, daemon=True)
            playback_thread.start()
            print("請保持受控文字框焦點。ClipAI 開始聆聽後，固定音檔會自動從喇叭播放；聽完再按第二次快捷鍵。")
        input("完成 ClipAI 的終態／取消後，回到此視窗按 Enter：")
        if playback_thread is not None:
            playback_thread.join(timeout=35)
            if not playback_result or playback_result[0] != "played":
                playback_stop.set()
                reason = playback_result[0] if playback_result else "audio_playback_incomplete"
                _write_blocked_report(
                    report_path, mode=args.mode, scenario=args.scenario,
                    run_nonce=run_nonce, reason_code=reason,
                    check_name="audio_playback",
                )
                print("固定音檔播放未確認；本輪不計為語音鏈路驗證。", file=sys.stderr)
                print(report_path)
                return 2
        _command(process, "observe")
        _wait_record(events_path, "observation")
        time.sleep(args.late_wait)
        _command(process, "observe")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if sum(record.get("kind") == "observation" for record in _records(events_path)) >= 2:
                break
            time.sleep(0.05)
    except (KeyboardInterrupt, EOFError, TimeoutError, BrokenPipeError) as exc:
        print(f"桌面執行未完成：{type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        playback_stop.set()
        if process.poll() is None:
            try:
                _command(process, "shutdown")
                process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                process.terminate()
                process.wait(timeout=5)
    if app_log.exists():
        with app_log.open("rb") as source:
            source.seek(log_offset)
            lines = source.read().decode("utf-8", errors="replace").splitlines()
    else:
        lines = []
    trace_lines = [line for line in lines if "Inline trace " in line]
    trace_path.write_text("\n".join(trace_lines) + ("\n" if trace_lines else ""), encoding="utf-8")
    report = assess(_records(events_path), trace_lines, mode=args.mode, scenario=args.scenario,
                    text_policy="nonempty" if args.freeform else "exact",
                    audio_playback_interval_ns=tuple(playback_interval_ns) if audio_file is not None and len(playback_interval_ns) == 2 else None)
    if audio_file is not None:
        report["audio_replay"] = {
            "source": "fixed_wav_speaker_playback",
            "sha256": hashlib.sha256(audio_file.read_bytes()).hexdigest(),
            "playback_returned": True,
            "trigger": "matching_inline_listening_trace",
            "reference_source": "hash_matched_fixture_manifest" if fixture_reference else "operator_supplied_or_unavailable",
            "start_monotonic_ns": playback_interval_ns[0],
            "end_monotonic_ns": playback_interval_ns[1],
            "microphone_input_independently_confirmed": False,
        }
        report["microphone_audio_source"] = "speaker_replay_triggered_input_not_independently_confirmed"
    if not trace_lines and not app_instance_is_running():
        report["checks"]["app_instance"] = "blocked"
        report["reason_code"] = "clipai_app_exited_during_run"
    report["run_nonce"] = run_nonce
    report["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report_path)
    app_check_values = [value for name, value in report["checks"].items() if name != "target_readback"]
    app_status = "fail" if "fail" in app_check_values else "blocked" if "blocked" in app_check_values else "pass"
    print(f"受控讀回：{report['target']['status']}；App trace：{app_status}；整體：{report['status']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
