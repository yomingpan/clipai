"""Public probe contracts against owned child processes (no UIA or user input)."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

import pytest

from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.platform.selection_uia import WindowsSelectionProbe
from ClipAI.platform.selection_uia_worker import NativeSelectionResult, worker_response


SOURCE = SelectionSource(ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")
pytestmark = pytest.mark.integration


@pytest.fixture
def children():
    processes = []
    yield processes
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def factory(children, body):
    def launch(*_args, **kwargs):
        process = subprocess.Popen(
            [getattr(sys, "_base_executable", sys.executable), "-u", "-c", body],
            **kwargs,
        )
        children.append(process)
        return process
    return launch


def response_program(payload):
    return "import sys\nfor line in sys.stdin:\n print(" + repr(json.dumps(payload)) + ", flush=True)\n"


def test_real_worker_reuses_then_retires_and_stop_is_terminal(children):
    probe = WindowsSelectionProbe(max_requests_per_worker=2, process_factory=factory(
        children, response_program({"status": "none", "worker_reusable": True}),
    ))
    try:
        for _ in range(2):
            assert probe.probe(SOURCE, None).status == "none"
        assert len(children) == 1 and children[0].poll() is not None
        assert probe.probe(SOURCE, None).status == "none"
        assert len(children) == 2
    finally:
        probe.stop()
    assert all(p.poll() is not None for p in children)
    probe.start()  # lazy start cannot reopen a terminal owner
    assert probe.probe(SOURCE, None).status == "cancelled"
    assert len(children) == 2
    probe.stop()


@pytest.mark.parametrize("payload", [
    {"status": "none"}, {"status": "selected", "text": 42, "worker_reusable": True},
    {"status": "none", "worker_reusable": "true"},
    {"status": "unknown", "reason": "renamed", "worker_reusable": False},
])
def test_real_malformed_or_retire_reply_reaps_process(children, payload):
    probe = WindowsSelectionProbe(process_factory=factory(children, response_program(payload)))
    try:
        assert probe.probe(SOURCE, None).status == "unknown"
        assert children[0].poll() is not None
    finally:
        probe.stop()


def test_diagnostic_spelling_does_not_determine_reuse(children):
    payload = worker_response(NativeSelectionResult(
        SelectionCaptureOutcome(reason="arbitrary_failed"), worker_reusable=True,
    ))
    probe = WindowsSelectionProbe(process_factory=factory(children, response_program(payload)))
    try:
        assert probe.probe(SOURCE, None).reason == "arbitrary_failed"
        probe.probe(SOURCE, None)
        assert len(children) == 1
    finally:
        probe.stop()


@pytest.mark.parametrize("mode", ["eof", "timeout", "cancel"])
def test_real_eof_timeout_and_cancellation_reap(children, mode):
    body = "import sys,time\nsys.stdin.readline()\n" + ("sys.exit(0)" if mode == "eof" else "time.sleep(30)")
    token = CancellationToken()
    probe = WindowsSelectionProbe(timeout_sec=0.4, process_factory=factory(children, body))
    timer = threading.Timer(0.1, token.cancel) if mode == "cancel" else None
    try:
        if timer:
            timer.start()
        result = probe.probe(SOURCE, token)
        assert result.status == ("cancelled" if mode == "cancel" else "unknown")
        assert children[0].poll() is not None
    finally:
        if timer:
            timer.cancel()
            timer.join()
        probe.stop()


def test_stop_settles_owned_and_overflow_concurrently(children):
    launched = threading.Condition()
    base = factory(children, "import sys,time\nsys.stdin.readline()\ntime.sleep(30)")
    def launch(*args, **kwargs):
        process = base(*args, **kwargs)
        with launched:
            launched.notify_all()
        return process
    probe = WindowsSelectionProbe(timeout_sec=30, process_factory=launch)
    results = []
    threads = [threading.Thread(target=lambda: results.append(probe.probe(SOURCE, None))) for _ in range(4)]
    try:
        for thread in threads:
            thread.start()
        with launched:
            assert launched.wait_for(lambda: len(children) == 4, timeout=5)
        started = time.monotonic()
        probe.stop()
        assert time.monotonic() - started < 2.0
        assert all(p.poll() is not None for p in children)
    finally:
        probe.stop()
        for thread in threads:
            thread.join(3)
    assert len(results) == 4
    assert all(result.status == "cancelled" for result in results)


def test_blocked_pipe_write_cannot_defeat_request_deadline(children):
    probe = WindowsSelectionProbe(timeout_sec=0.2, process_factory=factory(
        children, "import time; time.sleep(30)",
    ))
    # Exceed pipe capacity while the controlled process deliberately never reads.
    source = SelectionSource(SOURCE.window, "x" * (2 * 1024 * 1024))
    try:
        started = time.monotonic()
        assert probe.probe(source, None).reason == "uia_timeout"
        assert time.monotonic() - started < 2.0
        assert children[0].poll() is not None
    finally:
        probe.stop()


def test_stop_reports_late_launch_and_still_owns_its_cleanup(children):
    entered, release = threading.Event(), threading.Event()
    base = factory(children, response_program({"status": "none", "worker_reusable": True}))
    def launch(*args, **kwargs):
        entered.set()
        release.wait(5)
        return base(*args, **kwargs)
    probe = WindowsSelectionProbe(timeout_sec=30, process_factory=launch)
    failures = []
    def capture():
        try:
            probe.probe(SOURCE, None)
        except RuntimeError as error:
            failures.append(str(error))
    thread = threading.Thread(target=capture)
    thread.start()
    try:
        assert entered.wait(3)
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="cleanup"):
            probe.stop()
        assert time.monotonic() - started < 2.3
    finally:
        release.set()
        thread.join(3)
        probe.stop()
    assert len(children) == 1 and children[0].poll() is not None
    assert all("cleanup" in failure for failure in failures)
