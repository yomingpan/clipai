from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("CLIPAI_RUN_VOICE_WEBVIEW_INTEGRATION") != "1",
        reason="requires an interactive Windows desktop with Edge WebView2 Runtime",
    ),
]


class Host:
    def __init__(self) -> None:
        page = Path(__file__).with_name("fixtures") / "voice_webview_test_host.html"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "ClipAI.platform.voice_webview_host", "--test-page", str(page)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.events: queue.Queue[dict[str, object]] = queue.Queue()
        self.stderr: list[str] = []
        assert self.process.stdout is not None
        threading.Thread(target=self._read_events, daemon=True).start()
        assert self.process.stderr is not None
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def send(self, command: str, **payload: object) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"version": 1, "command": command, **payload}) + "\n")
        self.process.stdin.flush()

    def next(self, kind: str, timeout: float = 10.0) -> dict[str, object]:
        while True:
            try:
                event = self.events.get(timeout=timeout)
            except queue.Empty as exc:
                raise AssertionError(
                    f"Voice test host did not emit {kind!r}; exit={self.process.poll()!r}; stderr={''.join(self.stderr)!r}"
                ) from exc
            if event.get("kind") == kind:
                return event

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.send("shutdown")
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=5)

    def _read_events(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        self.stderr.extend(self.process.stderr)


def test_test_host_releases_fake_setup_and_capture_tracks_before_terminal() -> None:
    host = Host()
    try:
        assert host.next("test_loaded")["kind"] == "test_loaded"
        host.send("prepare", setup_id="setup-1", language="zh-TW")
        setup_state = host.next("test_state")
        assert setup_state["setup_track_stops"] == 1
        assert host.next("setup_ready")["setup_id"] == "setup-1"

        host.send("start", capture_id="capture-1", language="zh-TW", sequence_start=0)
        assert host.next("listening")["capture_id"] == "capture-1"
        host.send("stop", capture_id="capture-1")
        capture_state = host.next("test_state")
        assert capture_state["capture_track_stops"] == 1
        assert host.next("ended")["capture_id"] == "capture-1"
    finally:
        host.close()
