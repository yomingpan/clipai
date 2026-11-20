"""Probe the production WebView voice host with a fixed WAV played by speakers.

This bypasses the app shortcut and Paste path. It saves event kinds, bounded
audio levels, and literal error counts, never recognized or clipboard text.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4

if __package__:
    from .inline_dictation_controlled_target import _literal_character_errors
else:
    from inline_dictation_controlled_target import _literal_character_errors


ROOT = Path(__file__).resolve().parents[1]


def _reference(audio_file: Path) -> str:
    try:
        manifest = json.loads((audio_file.parent / "manifest.json").read_text(encoding="utf-8-sig"))
        digest = hashlib.sha256(audio_file.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""
    for item in manifest.get("fixtures", []) if isinstance(manifest, dict) else []:
        if (isinstance(item, dict) and item.get("file") == audio_file.name
                and item.get("sha256") == digest and isinstance(item.get("phrase"), str)
                and 0 < len(item["phrase"]) <= 256):
            return item["phrase"]
    return ""


def summarize(events: list[tuple[int, dict[str, object]]], *, playback: tuple[int, int] | None,
              reference: str, fixture_sha256: str) -> dict[str, object]:
    kinds = Counter(event.get("kind") for _, event in events)
    finals = [event.get("text") for _, event in events if event.get("kind") == "final"]
    transcript = "".join(value for value in finals if isinstance(value, str))
    errors = _literal_character_errors(reference, transcript) if reference and transcript else None
    levels = [
        float(event["level"]) for timestamp, event in events
        if event.get("kind") == "audio_level" and type(event.get("level")) in {int, float}
        and playback is not None and playback[0] <= timestamp <= playback[1]
    ]
    failure_types = sorted({
        str(event.get("failure")) for _, event in events
        if event.get("kind") in {"failed", "setup_failed"} and event.get("failure")
    })
    browser_error_codes = sorted({
        str(event.get("code")) for _, event in events
        if event.get("kind") == "probe_recognition_error"
        and event.get("code") in {"no-speech", "network", "audio-capture", "not-allowed", "aborted", "service-not-allowed"}
    })
    status = (
        "blocked" if kinds["test_loaded"] == 0 or kinds["setup_ready"] == 0 or kinds["listening"] == 0
        else "blocked" if playback is None
        else "fail" if kinds["ended"] == 0 or kinds["failed"] > 0 or not transcript
        else "pass"
    )
    reason_code = (
        "host_not_loaded" if kinds["test_loaded"] == 0
        else "microphone_setup_unavailable" if kinds["setup_ready"] == 0
        else "listening_not_observed" if kinds["listening"] == 0
        else "audio_playback_unavailable" if playback is None
        else "capture_not_ended" if kinds["ended"] == 0
        else "recognition_failed" if kinds["failed"] > 0
        else "no_final_transcript" if not transcript
        else ""
    )
    return {
        "schema_version": 1,
        "scope": "production_webview_host_fixed_wav_acoustic_probe_without_hotkey_or_paste",
        "status": status,
        "reason_code": reason_code,
        "fixture_sha256": fixture_sha256,
        "playback_start_monotonic_ns": playback[0] if playback else None,
        "playback_end_monotonic_ns": playback[1] if playback else None,
        "event_counts": {kind: kinds[kind] for kind in (
            "test_loaded", "setup_ready", "setup_blocked", "setup_failed", "listening",
            "audio_level", "interim", "final", "failed", "ended", "test_bridge_timeout",
        )},
        "failure_types": failure_types,
        "browser_error_codes": browser_error_codes,
        "playback_audio_level_samples": len(levels),
        "playback_peak_audio_level": round(max(levels), 4) if levels else None,
        "reference_codepoints": len(reference) if reference else None,
        "observed_codepoints": len(transcript),
        "literal_character_comparison_status": "measured" if errors is not None else "not_observed",
        "literal_character_errors": errors,
        "literal_character_error_rate": round(errors / len(reference), 3) if errors is not None else None,
        "microphone_input_independently_confirmed": False,
        "physical_hotkey_observed": False,
        "target_insertion_observed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-file", type=Path, required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--post-playback-wait", type=float, default=1.0)
    parser.add_argument("--diagnose-browser-errors", action="store_true",
                        help="instrument the temporary test-page copy to record allowlisted SpeechRecognition error codes")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("requires an interactive Windows desktop")
    import winsound
    audio_file = args.audio_file.resolve()
    if not audio_file.is_file() or audio_file.suffix.lower() != ".wav":
        parser.error("--audio-file must be an existing WAV")
    reference = _reference(audio_file)
    if not reference:
        parser.error("--audio-file must match a consented phrase and SHA-256 in its manifest.json")
    if not 0 <= args.post_playback_wait <= 10:
        parser.error("--post-playback-wait must be between 0 and 10 seconds")
    output = args.output.resolve()
    if output.exists():
        parser.error("--output already exists; use a new path for each run")
    profile_parent = Path(os.environ["LOCALAPPDATA"]) / "ClipAI" / "InlineValidationProfiles"
    profile_parent.mkdir(parents=True, exist_ok=True)
    profile = profile_parent / ("autonomous-" + uuid4().hex)
    profile.mkdir()
    page = profile / "test-page.html"
    command = [sys.executable, "-m", "ClipAI.platform.voice_webview_host",
               "--test-page", str(page), "--profile-root", str(profile)]
    process: subprocess.Popen[str] | None = None
    received: queue.Queue[tuple[int, dict[str, object]]] = queue.Queue()
    events: list[tuple[int, dict[str, object]]] = []
    playback: tuple[int, int] | None = None

    def read_events(stream) -> None:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                received.put((time.monotonic_ns(), value))

    def wait_for(kind: str, timeout: float, *, stop_on_failure: bool = True) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = received.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            events.append(event)
            if event[1].get("kind") == kind:
                return True
            if stop_on_failure and event[1].get("kind") in {"setup_blocked", "setup_failed", "failed", "test_bridge_timeout"}:
                return False
        return False

    def send(name: str, **payload: object) -> None:
        assert process is not None and process.stdin is not None
        process.stdin.write(json.dumps({"version": 1, "command": name, **payload}) + "\n")
        process.stdin.flush()

    try:
        source_page = (ROOT / "ClipAI" / "platform" / "voice_webview_host.html").read_text(encoding="utf-8")
        if args.diagnose_browser_errors:
            marker = "recognition.onerror = event => {"
            if source_page.count(marker) != 1:
                raise RuntimeError("SpeechRecognition error hook changed; diagnostic page not generated")
            source_page = source_page.replace(
                marker,
                marker + '\n        emit({kind: "probe_recognition_error", code: event.error});',
            )
        page.write_text(source_page, encoding="utf-8")
        process = subprocess.Popen(
            command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert process.stdout is not None
        threading.Thread(target=read_events, args=(process.stdout,), daemon=True).start()
        if wait_for("test_loaded", 30):
            send("prepare", setup_id="probe-setup", language=args.language)
            if wait_for("setup_ready", 15):
                send("start", capture_id="probe-capture", language=args.language, sequence_start=0)
                if wait_for("listening", 15):
                    try:
                        started = time.monotonic_ns()
                        winsound.PlaySound(str(audio_file), winsound.SND_FILENAME)
                        ended = time.monotonic_ns()
                        playback = (started, ended)
                        time.sleep(args.post_playback_wait)
                    except (OSError, RuntimeError):
                        pass
                    send("stop", capture_id="probe-capture")
                    wait_for("ended", 15, stop_on_failure=False)
        while True:
            try:
                events.append(received.get_nowait())
            except queue.Empty:
                break
    finally:
        if process is not None and process.poll() is None:
            try:
                send("shutdown")
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.terminate()
                process.wait(timeout=5)
        if profile.resolve().parent == profile_parent.resolve():
            shutil.rmtree(profile, ignore_errors=True)
    result = summarize(events, playback=playback, reference=reference,
                       fixture_sha256=hashlib.sha256(audio_file.read_bytes()).hexdigest())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(f"WebView voice host: {result['status']}; final events: {result['event_counts']['final']}; "
          f"audio samples during playback: {result['playback_audio_level_samples']}")
    return 0 if result["status"] == "pass" else 2 if result["status"] == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
