from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk

import pytest

from scripts import inline_dictation_controlled_target as target_module


def test_literal_character_errors_are_bounded_and_keep_no_text() -> None:
    score = target_module._literal_character_errors
    assert score("你好，世界", "你好世界") == 1
    assert score("abc", "axc") == 1
    assert score("abc", "abc!") == 1
    assert score("", "anything") is None
    assert score("x" * 257, "x") is None
    assert score("x", "x" * 1025) is None


@pytest.mark.integration
def test_controlled_target_reports_paste_readback_without_exporting_text(monkeypatch) -> None:
    monkeypatch.setattr(target_module, "clipboard_fingerprint", lambda: {"status": "observed", "formats": []})
    root = tk.Tk()
    root.withdraw()
    output = io.StringIO()
    target = target_module.ControlledTarget(
        root, output=output, expected_text="controlled private phrase", run_nonce="test-run",
    )
    try:
        target.emit("ready")
        target.editor.insert("1.0", "controlled private phrase")
        target.editor.bind_class("Text", "<<Paste>>", "")
        target.editor.event_generate("<<Paste>>")
        root.update()
        target.finish()
        records = [json.loads(line) for line in output.getvalue().splitlines()]

        assert [record["kind"] for record in records] == ["ready", "paste_observed"]
        assert records[-1]["target"]["matches_expected"] is True
        assert records[-1]["target"]["paste_count"] == 1
        assert records[-1]["target"]["literal_character_errors"] == 0
        assert records[-1]["target"]["reference_codepoints"] == len("controlled private phrase")
        assert records[-1]["run_nonce"] == "test-run"
        assert "controlled private phrase" not in output.getvalue()
    finally:
        root.destroy()


def test_clipboard_fingerprint_records_format_hashes_without_payload(monkeypatch) -> None:
    class Snapshot:
        formats = (type("Format", (), {"format_id": 13, "data": b"private clipboard"})(),)

    monkeypatch.setattr(target_module.SystemClipboard, "snapshot", lambda self: Snapshot())

    fingerprint = target_module.clipboard_fingerprint()

    assert fingerprint["status"] == "observed"
    assert fingerprint["formats"][0]["id"] == 13
    assert fingerprint["formats"][0]["bytes"] == len(b"private clipboard")
    assert "private clipboard" not in json.dumps(fingerprint)


@pytest.mark.integration
def test_controlled_target_process_accepts_observe_and_shutdown(tmp_path: Path) -> None:
    output = tmp_path / "target.jsonl"
    process = subprocess.Popen(
        [
            sys.executable, "-m", "scripts.inline_dictation_controlled_target",
            "--output", str(output), "--expected-text", "controlled phrase",
            "--run-nonce", "process-test",
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[2],
    )
    try:
        deadline = time.monotonic() + 8
        while (not output.exists() or "\"kind\": \"ready\"" not in output.read_text(encoding="utf-8")) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert output.exists() and "\"kind\": \"ready\"" in output.read_text(encoding="utf-8")
        assert process.stdin is not None
        process.stdin.write(b'{"command":"observe"}\n{"command":"shutdown"}\n')
        process.stdin.flush()
        assert process.wait(timeout=8) == 0
        assert process.stderr is not None
        assert process.stderr.read() == b""
        records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        assert [record["kind"] for record in records] == ["ready", "observation", "shutdown"]
        assert all(record["run_nonce"] == "process-test" for record in records)
        assert "controlled phrase" not in output.read_text(encoding="utf-8")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
