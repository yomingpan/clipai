from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import queue
import threading
import time
from typing import Any

from ClipAI.core.models import ExternalWindowRef, SelectionCaptureOutcome, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.platform.win32_api import configure_win32_api


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def capture_windows_source(target: ExternalWindowRef | None = None) -> SelectionSource | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    configure_win32_api(user32, ctypes.windll.kernel32)
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not hwnd or not thread or pid.value == os.getpid():
        return None
    token = f"hwnd:{int(hwnd):x}"
    if target is not None and (target.window_token != token or target.process_id != pid.value):
        return None
    info = _GuiThreadInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.hwndFocus:
        return None
    window = target or ExternalWindowRef(token, pid.value, 0)
    return SelectionSource(window, f"hwnd:{int(info.hwndFocus):x}")


class WindowsSelectionProbe:
    """Own one bounded UIA worker and isolate overlapping requests."""

    def __init__(
        self,
        *,
        timeout_sec: float = 2.0,
        max_requests_per_worker: int = 64,
        process_factory=subprocess.Popen,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._max_requests_per_worker = max_requests_per_worker
        self._process_factory = process_factory
        self._owned_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stopped = threading.Event()
        self._workers: set[_WorkerProcess] = set()
        self._owned_worker: _WorkerProcess | None = None
        self._owned_source: tuple[str, int] | None = None
        self._owned_requests = 0

    def start(self) -> None:
        """Workers are source-bound and therefore start lazily on first use."""

    def stop(self) -> None:
        deadline = time.monotonic() + 2.0
        with self._lifecycle_lock:
            self._stopped.set()
            workers = tuple(self._workers)
        # Initiate every cleanup before waiting: the budget is container-wide.
        for worker in workers:
            worker.begin_retirement()
        failed = False
        for worker in workers:
            if worker.retire(deadline):
                with self._lifecycle_lock:
                    self._workers.discard(worker)
            else:
                failed = True
        if failed:
            raise RuntimeError("Selection worker cleanup could not confirm process exit")

    def capture_source(self, target: ExternalWindowRef | None) -> SelectionSource | None:
        return capture_windows_source(target)

    def source_is_current(self, source: SelectionSource) -> bool:
        return capture_windows_source(source.window) == source

    def probe(self, source: SelectionSource, cancellation: CancellationToken | None) -> SelectionCaptureOutcome:
        if self._stopped.is_set() or (cancellation is not None and cancellation.is_cancelled):
            return SelectionCaptureOutcome(status="cancelled", strategy="uia")
        if self._owned_lock.acquire(blocking=False):
            try:
                return self._probe_owned(source, cancellation)
            finally:
                self._owned_lock.release()
        return self._probe_overflow(source, cancellation)

    def _probe_owned(
        self,
        source: SelectionSource,
        cancellation: CancellationToken | None,
    ) -> SelectionCaptureOutcome:
        source_key = (source.window.window_token, source.window.process_id)
        if self._owned_source != source_key:
            self._retire_owned()
        if self._owned_worker is None:
            try:
                self._owned_worker = self._start_worker()
                self._owned_source = source_key
                self._owned_requests = 0
            except Exception:
                self._retire_owned()
                if self._stopped.is_set():
                    return SelectionCaptureOutcome(status="cancelled", strategy="uia")
                return SelectionCaptureOutcome(reason="uia_unavailable", strategy="uia")

        outcome, healthy = self._owned_worker.request(
            _request_payload(source), cancellation, self._timeout_sec,
        )
        self._owned_requests += 1
        if not healthy or self._owned_requests >= self._max_requests_per_worker:
            self._retire_owned()
        return outcome

    def _probe_overflow(
        self,
        source: SelectionSource,
        cancellation: CancellationToken | None,
    ) -> SelectionCaptureOutcome:
        worker = None
        try:
            worker = self._start_worker()
            outcome, _healthy = worker.request(
                _request_payload(source), cancellation, self._timeout_sec,
            )
            return outcome
        except Exception:
            if self._stopped.is_set():
                return SelectionCaptureOutcome(status="cancelled", strategy="uia")
            return SelectionCaptureOutcome(reason="uia_unavailable", strategy="uia")
        finally:
            if worker is not None:
                self._retire_worker(worker)

    def _start_worker(self) -> _WorkerProcess:
        with self._lifecycle_lock:
            if self._stopped.is_set():
                raise RuntimeError("Selection probe is stopped")
            worker = _WorkerProcess(self._launch_process)
            self._workers.add(worker)
            return worker

    def _launch_process(self):
        return self._process_factory(
            # Windows venv python.exe can be a redirector with a child process.
            # Launch the real interpreter so killing this PID kills the UIA call.
            [
                getattr(sys, "_base_executable", sys.executable), "-c",
                "import json,runpy,sys; sys.path[:]=json.loads(sys.argv[1]); "
                "runpy.run_module('ClipAI.platform.selection_uia_worker',run_name='__main__')",
                json.dumps([str(Path(__file__).resolve().parents[2])] + [str(Path(p).resolve()) for p in sys.path if p]),
            ],
            cwd=str(Path(__file__).resolve().parents[2]),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _retire_worker(self, worker: _WorkerProcess) -> None:
        if not worker.retire(time.monotonic() + 2.0):
            raise RuntimeError("Selection worker cleanup could not confirm process exit")
        with self._lifecycle_lock:
            self._workers.discard(worker)

    def _retire_owned(self) -> None:
        if self._owned_worker is not None:
            self._retire_worker(self._owned_worker)
        self._owned_worker = None
        self._owned_source = None
        self._owned_requests = 0


def _request_payload(source: SelectionSource) -> str:
    return json.dumps({
            "window_token": source.window.window_token,
            "process_id": source.window.process_id,
            "observation_sequence": source.window.observation_sequence,
            "focus_token": source.focus_token,
        })


class _WorkerProcess:
    """Contain launch, blocking pipes and retirement behind bounded waits."""

    def __init__(self, launch) -> None:
        self._process: Any = None
        self._ready = threading.Event()
        self._retiring = threading.Event()
        self._retired = threading.Event()
        self._retirement_lock = threading.Lock()
        self._io_thread: threading.Thread | None = None

        def guarded_start() -> None:
            try:
                self._process = launch()
            except Exception:
                pass  # request reports unavailable; no native details escape.
            finally:
                self._ready.set()

        threading.Thread(target=guarded_start, daemon=True).start()

    def request(
        self,
        request: str,
        cancellation: CancellationToken | None,
        timeout_sec: float,
    ) -> tuple[SelectionCaptureOutcome, bool]:
        responses: queue.Queue[object] = queue.Queue(maxsize=1)
        try:
            def read_response() -> None:
                try:
                    self._ready.wait()
                    if self._retiring.is_set() or self._process is None:
                        responses.put("")
                        return
                    self._process.stdin.write(request + "\n")
                    self._process.stdin.flush()
                    responses.put(self._process.stdout.readline())
                except Exception as exc:
                    responses.put(exc)

            self._io_thread = threading.Thread(target=read_response, daemon=True)
            self._io_thread.start()
            deadline = time.monotonic() + timeout_sec
            while True:
                if self._retiring.is_set() or (cancellation is not None and cancellation.is_cancelled):
                    return SelectionCaptureOutcome(status="cancelled", strategy="uia"), False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if cancellation is not None and cancellation.is_cancelled:
                        return SelectionCaptureOutcome(status="cancelled", strategy="uia"), False
                    return SelectionCaptureOutcome(reason="uia_timeout", strategy="uia"), False
                try:
                    response = responses.get(timeout=min(0.02, remaining))
                except queue.Empty:
                    continue
                if isinstance(response, Exception) or not response:
                    return SelectionCaptureOutcome(reason="uia_worker_failed", strategy="uia"), False
                payload = json.loads(response)
                break
            status = payload.get("status")
            if type(payload.get("worker_reusable")) is not bool:
                return SelectionCaptureOutcome(reason="uia_invalid_result", strategy="uia"), False
            if not isinstance(payload.get("text", ""), str) or not isinstance(payload.get("reason", ""), str):
                return SelectionCaptureOutcome(reason="uia_invalid_result", strategy="uia"), False
            if status not in {"selected", "none", "unknown"}:
                return SelectionCaptureOutcome(reason="uia_invalid_result", strategy="uia"), False
            for capability in ("selection_detected", "copy_selection_only", "focus_restored"):
                if capability in payload and type(payload[capability]) is not bool:
                    return SelectionCaptureOutcome(reason="uia_invalid_result", strategy="uia"), False
            outcome = SelectionCaptureOutcome(
                text=payload.get("text", ""), status=status,
                reason=payload.get("reason", ""), strategy="uia",
                selection_detected=payload.get("selection_detected", False),
                copy_selection_only=payload.get("copy_selection_only") is True,
                focus_restored=payload.get("focus_restored") is True,
            )
            if self._retiring.is_set() or (cancellation is not None and cancellation.is_cancelled):
                return SelectionCaptureOutcome(status="cancelled", strategy="uia"), False
            return outcome, payload["worker_reusable"]
        except Exception:
            return SelectionCaptureOutcome(reason="uia_invalid_result", strategy="uia"), False

    def begin_retirement(self) -> None:
        with self._retirement_lock:
            if self._retiring.is_set():
                return
            self._retiring.set()
            threading.Thread(target=self._cleanup, daemon=True).start()

    def retire(self, deadline: float) -> bool:
        self.begin_retirement()
        return self._retired.wait(max(0.0, deadline - time.monotonic()))

    def _cleanup(self) -> None:
        # A slow launch remains owned even after stop reports its deadline.
        self._ready.wait()
        process = self._process
        if process is None:
            self._retired.set()
            return

        def close_input() -> None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except (OSError, ValueError):
                pass

        # close() may contend with a blocked pipe write. Never block the caller.
        closer = threading.Thread(target=close_input, daemon=True)
        closer.start()
        try:
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1.0)
            if process.poll() is None:
                return
            if self._io_thread is not None:
                self._io_thread.join()
            closer.join()
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            self._retired.set()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return  # Retain ownership; bounded retire reports cleanup failure.
