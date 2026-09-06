"""Opt-in Windows smoke: owns a temporary RichTextBox, never reads user text."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from ClipAI.core.models import ExternalWindowRef
from ClipAI.core.state import CancellationToken
from ClipAI.platform.external_window import SystemExternalWindowActivator
from ClipAI.platform.selection_uia import WindowsSelectionProbe


@pytest.mark.integration
@pytest.mark.skipif(os.name != "nt", reason="Windows UI Automation")
def test_real_uia_selected_same_text_and_caret_only(tmp_path):
    command = tmp_path / "command.json"
    ready = tmp_path / "ready.json"
    process = subprocess.Popen(
        [getattr(sys, "_base_executable", sys.executable), str(Path(__file__).resolve()), "--host", str(command), str(ready)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[2])] + [str(Path(p).resolve()) for p in sys.path if p])},
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        text = "prefix\n反白內容：α + β = 3\nsuffix"
        for sequence, (start, length) in enumerate([(7, 15), (7, 15), (7, 0)], 1):
            command.write_text(json.dumps({"sequence": sequence, "text": text, "start": start, "length": length}), encoding="utf-8")
            deadline = time.monotonic() + 15
            payload = None
            while time.monotonic() < deadline:
                assert process.poll() is None, "test UI host exited"
                try:
                    candidate = json.loads(ready.read_text(encoding="utf-8"))
                    if candidate["sequence"] == sequence:
                        payload = candidate
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.05)
            assert payload is not None, "test UI host did not become ready"
            probe = WindowsSelectionProbe(timeout_sec=5)
            target = ExternalWindowRef(payload["window_token"], payload["process_id"], 0)
            activation = SystemExternalWindowActivator().activate(target, CancellationToken())
            assert activation.activated, activation
            source = probe.capture_source(target)
            assert source is not None, "test UI host did not receive foreground focus"
            result = probe.probe(source, None)
            assert probe.source_is_current(source)
            assert result.status == ("selected" if length else "none"), result
            if length:
                assert result.text == payload["selected"]
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def _host(command_path: Path, ready_path: Path) -> None:
    import clr

    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import Application, Form, RichTextBox, DockStyle, Timer

    form = Form()
    form.Text = "ClipAI selection integration test"
    form.Width, form.Height = 420, 220
    box = RichTextBox()
    box.Dock = DockStyle.Fill
    form.Controls.Add(box)
    state = {"sequence": 0}

    def tick(_sender, _event):
        try:
            payload = json.loads(command_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if state["sequence"] == payload["sequence"]:
            return
        box.Text = payload["text"]
        form.Activate()
        box.Focus()
        box.Select(payload["start"], payload["length"])
        state["sequence"] = payload["sequence"]
        ready_path.write_text(json.dumps({
            "sequence": payload["sequence"],
            "window_token": f"hwnd:{form.Handle.ToInt64():x}",
            "process_id": os.getpid(),
            "selected": str(box.SelectedText),
        }), encoding="utf-8")

    timer = Timer()
    timer.Interval = 100
    timer.Tick += tick
    timer.Start()
    Application.Run(form)


if __name__ == "__main__":
    _host(Path(sys.argv[2]), Path(sys.argv[3]))
