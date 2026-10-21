"""Owned UIA/CLR preload only: no source capture, text or clipboard access."""

import json
import os
import subprocess
import threading
import time

import pytest

from ClipAI.platform.selection_uia import WindowsSelectionProbe

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != "nt", reason="Windows UIA")]


def test_real_standby_preloads_clr_without_source_and_stops_within_shared_budget():
    processes = []
    readiness = []
    ready = threading.Event()

    def launch(*args, **kwargs):
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        original = process.stdout
        class Output:
            def readline(self):
                line = original.readline()
                payload = json.loads(line)
                readiness.append(payload)
                ready.set()
                return line
            def close(self):
                original.close()
        process.stdout = Output()
        return process

    probe = WindowsSelectionProbe(standby=True, process_factory=launch)
    try:
        probe.start()
        assert ready.wait(10), "UIA preload did not settle"
        assert readiness == [{"uia_ready": True}]
        assert len(processes) == 1
        started = time.monotonic()
        probe.stop()
        assert time.monotonic() - started <= 2.0
        assert processes[0].poll() is not None
    finally:
        probe.stop()
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
