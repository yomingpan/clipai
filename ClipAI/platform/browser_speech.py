from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

from ClipAI.core.voice import (
    VoiceCaptureId,
    VoiceEngineEnded,
    VoiceEngineEvent,
    VoiceEngineFailed,
    VoiceEngineFinalSegment,
    VoiceEngineInterim,
    VoiceEngineListening,
    VoiceEngineSetupBlocked,
    VoiceEngineSetupFailed,
    VoiceEngineSetupReady,
    VoiceLanguage,
    VoiceSetupId,
    VoiceTransportFailure,
)


VOICE_PROTOCOL_VERSION = 1


class BrowserSpeechWebView2Engine:
    """Own the WebView2 process and JSON transport, never Voice product policy."""

    def __init__(self, event_sink: Callable[[VoiceEngineEvent], None], *, process_factory: Callable[..., Any] = subprocess.Popen) -> None:
        self._event_sink = event_sink
        self._process_factory = process_factory
        self._process: Any | None = None
        self._setup_id: VoiceSetupId | None = None
        self._capture_id: VoiceCaptureId | None = None
        self._terminal_captures: set[VoiceCaptureId] = set()
        self._lock = threading.RLock()

    def prepare(self, setup_id: VoiceSetupId, language: VoiceLanguage) -> None:
        with self._lock:
            self._ensure_process()
            self._setup_id = setup_id
            self._send({"command": "prepare", "setup_id": setup_id, "language": language})

    def start_capture(self, capture_id: VoiceCaptureId, language: VoiceLanguage, *, sequence_start: int = 0) -> None:
        with self._lock:
            self._ensure_process()
            self._capture_id = capture_id
            self._terminal_captures.discard(capture_id)
            self._send({"command": "start", "capture_id": capture_id, "language": language, "sequence_start": sequence_start})

    def stop_capture(self, capture_id: VoiceCaptureId) -> None:
        self._send({"command": "stop", "capture_id": capture_id})

    def cancel_capture(self, capture_id: VoiceCaptureId) -> None:
        self._send({"command": "cancel", "capture_id": capture_id})

    def shutdown(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            self._setup_id = None
            self._capture_id = None
        if process is None:
            return
        try:
            self._write(process, {"version": VOICE_PROTOCOL_VERSION, "command": "shutdown"})
            process.wait(timeout=2)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def _ensure_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        process = self._process_factory(
            [sys.executable, "-m", "ClipAI.platform.voice_webview_host"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._process = process
        threading.Thread(target=self._read_events, args=(process,), daemon=True).start()

    def _send(self, payload: dict[str, object]) -> None:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                raise BrokenPipeError("Browser Speech host is unavailable")
            self._write(process, {"version": VOICE_PROTOCOL_VERSION, **payload})

    @staticmethod
    def _write(process: Any, payload: dict[str, object]) -> None:
        if process.stdin is None:
            raise BrokenPipeError("Browser Speech host stdin is unavailable")
        process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
        process.stdin.flush()

    def _read_events(self, process: Any) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                event = _decode_event(line)
                if event is not None:
                    self._deliver(process, event)
        self._handle_eof(process)

    def _deliver(self, process: Any, event: VoiceEngineEvent) -> None:
        with self._lock:
            if process is not self._process:
                return
            if isinstance(event, (VoiceEngineSetupReady, VoiceEngineSetupBlocked, VoiceEngineSetupFailed)):
                if event.setup_id != self._setup_id:
                    return
                self._setup_id = None
            else:
                if event.capture_id != self._capture_id:
                    return
                if isinstance(event, VoiceEngineEnded):
                    if event.capture_id in self._terminal_captures:
                        return
                    self._terminal_captures.add(event.capture_id)
                    self._capture_id = None
                elif isinstance(event, VoiceEngineFailed):
                    if event.capture_id in self._terminal_captures:
                        return
            sink = self._event_sink
        sink(event)

    def _handle_eof(self, process: Any) -> None:
        with self._lock:
            if process is not self._process:
                return
            self._process = None
            setup_id, self._setup_id = self._setup_id, None
            capture_id, self._capture_id = self._capture_id, None
            if capture_id is not None:
                self._terminal_captures.add(capture_id)
        if setup_id is not None:
            self._event_sink(VoiceEngineSetupFailed(setup_id, VoiceTransportFailure.PROCESS_CRASHED))
        if capture_id is not None:
            self._event_sink(VoiceEngineFailed(capture_id, VoiceTransportFailure.PROCESS_CRASHED))
            self._event_sink(VoiceEngineEnded(capture_id))


def _decode_event(line: str) -> VoiceEngineEvent | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("version") != VOICE_PROTOCOL_VERSION:
        return None
    kind = payload.get("kind")
    if kind not in {"setup_ready", "setup_blocked", "setup_failed", "listening", "interim", "final", "ended", "failed"}:
        return None
    if kind == "setup_ready":
        setup_id = str(payload.get("setup_id") or "")
        return VoiceEngineSetupReady(VoiceSetupId(setup_id)) if setup_id else None
    if kind == "setup_blocked":
        setup_id = str(payload.get("setup_id") or "")
        return VoiceEngineSetupBlocked(VoiceSetupId(setup_id)) if setup_id else None
    if kind == "setup_failed":
        setup_id = str(payload.get("setup_id") or "")
        return VoiceEngineSetupFailed(VoiceSetupId(setup_id), _failure(payload), str(payload.get("detail") or "")) if setup_id else None
    capture_value = str(payload.get("capture_id") or "")
    if not capture_value:
        return None
    capture_id = VoiceCaptureId(capture_value)
    if kind == "listening":
        return VoiceEngineListening(capture_id)
    if kind == "interim":
        return VoiceEngineInterim(capture_id, str(payload.get("text") or ""))
    if kind == "final":
        try:
            sequence = int(payload["sequence"])
        except (KeyError, TypeError, ValueError):
            return None
        return VoiceEngineFinalSegment(capture_id, sequence, str(payload.get("text") or ""))
    if kind == "ended":
        return VoiceEngineEnded(capture_id)
    if kind == "failed":
        return VoiceEngineFailed(capture_id, _failure(payload), str(payload.get("detail") or ""))
    return None


def _failure(payload: dict[str, object]) -> VoiceTransportFailure:
    try:
        return VoiceTransportFailure(str(payload.get("failure") or "initialization_failed"))
    except ValueError:
        return VoiceTransportFailure.INITIALIZATION_FAILED
