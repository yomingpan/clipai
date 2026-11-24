"""Content-free new-source UIA standby A/B and owned-worker resource evidence."""

from ClipAI.support.statistics import percentile

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import threading
import time

from ClipAI.core.models import ExternalWindowRef
from ClipAI.core.state import CancellationToken
from ClipAI.platform.external_window import SystemExternalWindowActivator
from ClipAI.platform.selection_uia import WindowsSelectionProbe
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.selection_capture import SelectionCaptureCoordinator
from scripts.selection_desktop_loop import _OwnedHost, _ReadOnlyAdapter, _RetryingClipboard, _text_sha256, fingerprint


def summarize(records, *, standby, private_mb, max_workers, workers_after_stop):
    times = [record["elapsed_ms"] for record in records]
    latencies = {"p50": percentile(times, .5), "p95": percentile(times, .95), "max": max(times)} if times else {"p50": None, "p95": None, "max": None}
    slow = sum(value > 1000 for value in times)
    unknown = sum(record["unknown_as_none"] for record in records)
    selected = sum(record["selected"] for record in records)
    resources = bool(private_mb) and max_workers <= (2 if standby else 1) and all(value <= 60 for value in private_mb) and workers_after_stop == 0
    performance = bool(times) and latencies["p50"] <= 300 and latencies["p95"] <= 1000 and slow/len(times) <= .02
    return {
        "schema": 1, "gate": "uia-standby-new-source", "standby": standby,
        "new_source_cases": len(records), "selected_cases": selected,
        "latency_ms": latencies, "over_1000_ms": slow,
        "unknown_as_none": unknown, "worker_private_mb": private_mb,
        "max_workers": max_workers, "workers_after_stop": workers_after_stop,
        "resource_passed": resources, "performance_passed": performance,
        "content_recorded": False,
        "passed": len(records) >= 50 and selected == len(records) and unknown == 0 and resources and performance,
    }


class _Memory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "peak_working", "working", "peak_paged", "paged", "peak_nonpaged",
            "nonpaged", "pagefile", "peak_pagefile", "private",
        )
    ]


def _private_mb(process):
    info = _Memory()
    info.cb = ctypes.sizeof(info)
    api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    api.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Memory), wintypes.DWORD]
    api.restype = wintypes.BOOL
    if not api(int(process._handle), ctypes.byref(info), info.cb):
        raise OSError(ctypes.get_last_error())
    return round(info.private/1024**2, 3)


def measure(*, standby: bool, cases: int, interval_ms: int):
    processes, hosts, records, memory = [], [], [], []
    process_lock = threading.Lock()
    max_workers = 0
    def launch(*args, **kwargs):
        nonlocal max_workers
        process = subprocess.Popen(*args, **kwargs)
        with process_lock:
            processes.append(process)
            max_workers = max(max_workers, sum(item.poll() is None for item in processes))
        return process
    clipboard = _RetryingClipboard()
    original = clipboard.snapshot()
    original_sequence = clipboard.sequence_number()
    original_hash = fingerprint(original)
    probe = WindowsSelectionProbe(standby=standby, process_factory=launch)
    coordinator = SelectionCaptureCoordinator(ClipboardTransactionCoordinator(clipboard), _ReadOnlyAdapter(), probe)
    activator = SystemExternalWindowActivator(modifier_is_pressed=lambda _: False)
    cleanup_failed = False
    clipboard_preserved = True
    stop_ms = None
    try:
        probe.start()
        for _ in range(2):
            hosts.append(_OwnedHost())
        # Each alternating HWND/PID forces a real new-source worker binding.
        for index in range(cases):
            host = hosts[index % 2]
            payload = host.configure("focus_moved")
            target = ExternalWindowRef(payload["window_token"], payload["process_id"], index)
            if not activator.activate(target, CancellationToken()).activated:
                raise RuntimeError("controlled_focus_unavailable")
            payload = host.configure("selected")
            request = coordinator.begin_capture(target)
            started = time.perf_counter()
            outcome = coordinator.capture(request=request)
            elapsed = (time.perf_counter()-started)*1000
            records.append({
                "elapsed_ms": round(elapsed, 3),
                "selected": outcome.status == "selected" and _text_sha256(outcome.text) == payload["selected_sha256"],
                "unknown_as_none": outcome.status == "none" and outcome.reason in {"source_changed", "uia_timeout", "unsupported", "cancelled"},
            })
            clipboard_preserved &= fingerprint(clipboard.snapshot()) == original_hash and clipboard.writes == 0
            time.sleep(interval_ms/1000)
            with process_lock:
                active = [item for item in processes if item.poll() is None]
            memory.extend(_private_mb(item) for item in active)
            if (index+1) % 10 == 0:
                print(json.dumps({"cases": index+1, "standby": standby, "selected": sum(row["selected"] for row in records)}), flush=True)
    finally:
        started = time.perf_counter()
        try:
            probe.stop()
        except RuntimeError:
            cleanup_failed = True
        stop_ms = round((time.perf_counter()-started)*1000, 3)
        try:
            for host in hosts:
                host.close()
        finally:
            clipboard.restore_if_unchanged(original, original_sequence)
    report = summarize(records, standby=standby, private_mb=sorted(memory, reverse=True)[:2], max_workers=max_workers, workers_after_stop=sum(item.poll() is None for item in processes))
    report.update({"stop_ms": stop_ms, "cleanup_failed": cleanup_failed, "clipboard_preserved": clipboard_preserved, "interval_ms": interval_ms, "device_evidence": True})
    report["passed"] &= not cleanup_failed and clipboard_preserved and stop_ms <= 2000
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standby", choices=("on", "off"), required=True)
    parser.add_argument("--cases", type=int, default=50)
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.cases < 1 or args.interval_ms < 0:
        parser.error("cases must be positive and interval nonnegative")
    report = measure(standby=args.standby == "on", cases=args.cases, interval_ms=args.interval_ms)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
