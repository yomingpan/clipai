from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ClipAI.core.voice import (
    VoiceCaptureId,
    VoiceEngineEnded,
    VoiceEngineAudioLevel,
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
from ClipAI.platform.voice_webview_profile import reset_voice_webview_profile


VOICE_PROTOCOL_VERSION = 1
CAPTURE_START_TIMEOUT_SECONDS = 15.0
CAPTURE_STOP_TIMEOUT_SECONDS = 5.0


def _schedule_capture_start_timeout(delay_seconds: float, callback: Callable[[], None]) -> threading.Timer:
    timer = threading.Timer(delay_seconds, callback)
    timer.daemon = True
    timer.start()
    return timer


class BrowserSpeechWebView2Engine:
    """Own the WebView2 process and JSON transport, never Voice product policy."""

    def __init__(
        self,
        event_sink: Callable[[VoiceEngineEvent], None],
        *,
        process_factory: Callable[..., Any] = subprocess.Popen,
        capture_start_timeout_schedule: Callable[[float, Callable[[], None]], object] = _schedule_capture_start_timeout,
        profile_root: Path | None = None,
        on_process_started: Callable[[int], None] = lambda _process_id: None,
        on_process_stopped: Callable[[int], None] = lambda _process_id: None,
    ) -> None:
        self._event_sink = event_sink
        self._process_factory = process_factory
        self._capture_start_timeout_schedule = capture_start_timeout_schedule
        self._profile_root = profile_root
        self._on_process_started = on_process_started
        self._on_process_stopped = on_process_stopped
        self._process: Any | None = None
        self._setup_id: VoiceSetupId | None = None
        self._capture_id: VoiceCaptureId | None = None
        self._capture_start_timeout: tuple[VoiceCaptureId, object, object] | None = None
        self._capture_stop_timeout: tuple[VoiceCaptureId, object, object] | None = None
        self._terminal_captures: set[VoiceCaptureId] = set()
        self._lock = threading.RLock()

    def prepare(self, setup_id: VoiceSetupId, language: VoiceLanguage) -> None:
        try:
            with self._lock:
                self._setup_id = setup_id
                self._ensure_process()
                self._send({"command": "prepare", "setup_id": setup_id, "language": language})
        except (BrokenPipeError, OSError, ValueError):
            self._settle_setup_write_failure(setup_id)

    def start_capture(self, capture_id: VoiceCaptureId, language: VoiceLanguage, *, sequence_start: int = 0) -> None:
        try:
            with self._lock:
                self._capture_id = capture_id
                self._terminal_captures.discard(capture_id)
                self._cancel_capture_stop_timeout()
                self._ensure_process()
                self._send({"command": "start", "capture_id": capture_id, "language": language, "sequence_start": sequence_start})
                self._start_capture_timeout(capture_id)
        except (BrokenPipeError, OSError, ValueError):
            self._settle_capture_write_failure(capture_id)

    def stop_capture(self, capture_id: VoiceCaptureId) -> None:
        self._request_capture_termination(capture_id, "stop")

    def cancel_capture(self, capture_id: VoiceCaptureId) -> None:
        self._request_capture_termination(capture_id, "cancel")

    def reset_permission_profile(self) -> None:
        """Forget only this app-owned WebView profile after a user requests repair."""
        self.shutdown()
        reset_voice_webview_profile(self._profile_root or Path.cwd())

    def _request_capture_termination(self, capture_id: VoiceCaptureId, command: str) -> None:
        try:
            with self._lock:
                if self._capture_id != capture_id or capture_id in self._terminal_captures:
                    return
                self._send({"command": command, "capture_id": capture_id})
                self._start_capture_stop_timeout(capture_id)
        except (BrokenPipeError, OSError, ValueError):
            self._settle_capture_write_failure(capture_id)

    def shutdown(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            self._setup_id = None
            self._capture_id = None
            self._cancel_capture_start_timeout()
            self._cancel_capture_stop_timeout()
        if process is None:
            return
        try:
            self._write(process, {"version": VOICE_PROTOCOL_VERSION, "command": "shutdown"})
            process.wait(timeout=2)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            self._terminate_process(process)
        finally:
            self._close_transport(process)
            self._notify_process_stopped(process)

    def _ensure_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        command = [sys.executable, "-m", "ClipAI.platform.voice_webview_host"]
        if self._profile_root is not None:
            command.extend(["--profile-root", str(self._profile_root)])
        process = self._process_factory(
            command,
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
        self._notify_process_started(process)
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

    @staticmethod
    def _close_transport(process: Any) -> None:
        for stream_name in ("stdin", "stdout"):
            stream = getattr(process, stream_name, None)
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except OSError:
                    pass

    @staticmethod
    def _terminate_process(process: Any) -> None:
        try:
            process.terminate()
        except OSError:
            return
        try:
            process.wait(timeout=2)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.kill()
        except OSError:
            return
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass

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
                if isinstance(event, VoiceEngineListening):
                    self._cancel_capture_start_timeout()
                elif isinstance(event, VoiceEngineEnded):
                    if event.capture_id in self._terminal_captures:
                        return
                    self._terminal_captures.add(event.capture_id)
                    self._capture_id = None
                    self._cancel_capture_start_timeout()
                    self._cancel_capture_stop_timeout()
                elif isinstance(event, VoiceEngineFailed):
                    if event.capture_id in self._terminal_captures:
                        return
                    self._terminal_captures.add(event.capture_id)
                    self._capture_id = None
                    self._cancel_capture_start_timeout()
                    self._cancel_capture_stop_timeout()
            sink = self._event_sink
        sink(event)

    def _handle_eof(self, process: Any) -> None:
        with self._lock:
            if process is not self._process:
                return
            self._process = None
            setup_id, self._setup_id = self._setup_id, None
            capture_id, self._capture_id = self._capture_id, None
            self._cancel_capture_start_timeout()
            self._cancel_capture_stop_timeout()
            if capture_id is not None:
                self._terminal_captures.add(capture_id)
        self._notify_process_stopped(process)
        if setup_id is not None:
            self._event_sink(VoiceEngineSetupFailed(setup_id, VoiceTransportFailure.PROCESS_CRASHED))
        if capture_id is not None:
            self._event_sink(VoiceEngineFailed(capture_id, VoiceTransportFailure.PROCESS_CRASHED))

    def _settle_setup_write_failure(self, setup_id: VoiceSetupId) -> None:
        with self._lock:
            if self._setup_id != setup_id:
                return
            self._setup_id = None
            self._discard_broken_process()
        self._event_sink(VoiceEngineSetupFailed(setup_id, VoiceTransportFailure.INITIALIZATION_FAILED))

    def _settle_capture_write_failure(self, capture_id: VoiceCaptureId) -> None:
        with self._lock:
            if self._capture_id != capture_id or capture_id in self._terminal_captures:
                return
            self._capture_id = None
            self._terminal_captures.add(capture_id)
            self._cancel_capture_start_timeout()
            self._cancel_capture_stop_timeout()
            self._discard_broken_process()
        self._event_sink(VoiceEngineFailed(capture_id, VoiceTransportFailure.PROCESS_CRASHED))

    def _start_capture_timeout(self, capture_id: VoiceCaptureId) -> None:
        self._cancel_capture_start_timeout()
        generation = object()
        timer = self._capture_start_timeout_schedule(
            CAPTURE_START_TIMEOUT_SECONDS,
            lambda: self._expire_capture_start(capture_id, generation),
        )
        self._capture_start_timeout = (capture_id, generation, timer)

    def _cancel_capture_start_timeout(self) -> None:
        timeout, self._capture_start_timeout = self._capture_start_timeout, None
        if timeout is not None and hasattr(timeout[2], "cancel"):
            timeout[2].cancel()

    def _start_capture_stop_timeout(self, capture_id: VoiceCaptureId) -> None:
        self._cancel_capture_start_timeout()
        self._cancel_capture_stop_timeout()
        generation = object()
        timer = self._capture_start_timeout_schedule(
            CAPTURE_STOP_TIMEOUT_SECONDS,
            lambda: self._expire_capture_stop(capture_id, generation),
        )
        self._capture_stop_timeout = (capture_id, generation, timer)

    def _cancel_capture_stop_timeout(self) -> None:
        timeout, self._capture_stop_timeout = self._capture_stop_timeout, None
        if timeout is not None and hasattr(timeout[2], "cancel"):
            timeout[2].cancel()

    def _expire_capture_start(self, capture_id: VoiceCaptureId, generation: object) -> None:
        with self._lock:
            timeout = self._capture_start_timeout
            if timeout is None or timeout[0] != capture_id or timeout[1] is not generation:
                return
            self._capture_start_timeout = None
            if self._capture_id != capture_id or capture_id in self._terminal_captures:
                return
            self._capture_id = None
            self._terminal_captures.add(capture_id)
            self._discard_broken_process()
        self._event_sink(VoiceEngineFailed(capture_id, VoiceTransportFailure.TIMEOUT))

    def _expire_capture_stop(self, capture_id: VoiceCaptureId, generation: object) -> None:
        with self._lock:
            timeout = self._capture_stop_timeout
            if timeout is None or timeout[0] != capture_id or timeout[1] is not generation:
                return
            self._capture_stop_timeout = None
            if self._capture_id != capture_id or capture_id in self._terminal_captures:
                return
            self._capture_id = None
            self._terminal_captures.add(capture_id)
            self._discard_broken_process()
        self._event_sink(VoiceEngineFailed(capture_id, VoiceTransportFailure.TIMEOUT))

    def _discard_broken_process(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            self._terminate_process(process)
        if process is not None:
            self._close_transport(process)
            self._notify_process_stopped(process)

    def _notify_process_stopped(self, process: Any) -> None:
        try:
            self._on_process_stopped(int(process.pid))
        except (AttributeError, TypeError, ValueError):
            pass

    def _notify_process_started(self, process: Any) -> None:
        try:
            self._on_process_started(int(process.pid))
        except (AttributeError, TypeError, ValueError):
            pass


def _decode_event(line: str) -> VoiceEngineEvent | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("version") != VOICE_PROTOCOL_VERSION:
        return None
    kind = payload.get("kind")
    if kind not in {"setup_ready", "setup_blocked", "setup_failed", "listening", "interim", "audio_level", "final", "ended", "failed"}:
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
    if kind == "audio_level":
        try:
            level = float(payload["level"])
            return VoiceEngineAudioLevel(capture_id, level) if 0.0 <= level <= 1.0 else None
        except (KeyError, TypeError, ValueError):
            return None
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
