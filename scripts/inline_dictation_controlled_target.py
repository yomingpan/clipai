"""Isolated Tk paste target with content-safe, read-back observations.

Run this on an interactive Windows desktop. JSON commands on stdin are
``observe``, ``reset``, ``focus``, ``select`` (start/end Tk indices), and
``shutdown``. The JSONL output never contains the target or clipboard text.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from typing import TextIO

from ClipAI.platform.clipboard import SystemClipboard


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clipboard_fingerprint() -> dict[str, object]:
    """Read only; format hashes can prove preservation without exporting data."""
    sampled_at_ns = time.monotonic_ns()
    try:
        snapshot = SystemClipboard().snapshot()
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__, "sampled_at_monotonic_ns": sampled_at_ns}
    return {
        "status": "observed",
        "sampled_at_monotonic_ns": sampled_at_ns,
        "formats": [
            {"id": item.format_id, "bytes": len(item.data), "sha256": _digest(item.data)}
            for item in snapshot.formats
        ],
    }


class ControlledTarget:
    def __init__(self, root: tk.Tk, *, output: TextIO, expected_text: str, run_nonce: str) -> None:
        self.root = root
        self.output = output
        self.expected_digest = _digest(expected_text.encode("utf-8"))
        self.run_nonce = run_nonce
        self.paste_count = 0
        self.commands: queue.Queue[dict[str, object]] = queue.Queue()
        self._records: queue.Queue[dict[str, object] | None] = queue.Queue()
        self._writer = threading.Thread(target=self._write_records, daemon=True)
        self._writer.start()
        self.editor = tk.Text(root, width=72, height=12, wrap="word")
        self.editor.pack(fill="both", expand=True)
        self.editor.bind("<<Paste>>", self._on_paste, add="+")
        self.editor.bind("<KeyPress-Escape>", self._on_escape, add="+")
        self.root.after(20, self._drain_commands)

    def _write_records(self) -> None:
        while True:
            record = self._records.get()
            if record is None:
                return
            if record.get("kind") != "command_error":
                record["clipboard"] = clipboard_fingerprint()
            self.output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self.output.flush()

    def finish(self) -> None:
        self._records.put(None)
        self._writer.join()

    def emit(self, kind: str, *, key_modifier_state: int | None = None) -> None:
        text = self.editor.get("1.0", "end-1c")
        text_bytes = text.encode("utf-8")
        text_digest = _digest(text_bytes)
        selection = self.editor.tag_ranges("sel")
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            foreground = int(user32.GetForegroundWindow() or 0)
            child_hwnd = int(self.root.winfo_id())
            hwnd = int(user32.GetParent(child_hwnd) or child_hwnd)
            focus = {"foreground_hwnd": foreground, "target_hwnd": hwnd, "target_is_foreground": foreground == hwnd}
        except (AttributeError, OSError):
            focus = {"target_is_foreground": None}
        record = {
            "schema_version": 1,
            "kind": kind,
            "run_nonce": self.run_nonce,
            "monotonic_ns": time.monotonic_ns(),
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "target": {
                "sha256": text_digest,
                "utf8_bytes": len(text_bytes),
                "matches_expected": text_digest == self.expected_digest,
                "insert_index": self.editor.index("insert"),
                "selection": [str(index) for index in selection],
                "paste_count": self.paste_count,
                **focus,
            },
        }
        if key_modifier_state is not None:
            record["key_modifier_state"] = key_modifier_state
        self._records.put(record)

    def _on_paste(self, _event: tk.Event) -> None:
        self.paste_count += 1
        self.root.after_idle(lambda: self.emit("paste_observed"))

    def _on_escape(self, event: tk.Event) -> None:
        self.emit("escape_observed", key_modifier_state=int(event.state))

    def handle(self, command: dict[str, object]) -> None:
        action = command.get("command")
        if action == "observe":
            self.emit("observation")
        elif action == "reset":
            self.editor.delete("1.0", "end")
            self.paste_count = 0
            self.emit("reset")
        elif action == "focus":
            self.root.lift()
            self.editor.focus_force()
            self.root.after_idle(lambda: self.emit("focus_requested"))
        elif action == "select":
            start, end = command.get("start"), command.get("end")
            if not isinstance(start, str) or not isinstance(end, str):
                raise ValueError("select requires start and end indices")
            self.editor.tag_remove("sel", "1.0", "end")
            self.editor.tag_add("sel", start, end)
            self.editor.mark_set("insert", end)
            self.emit("selection_set")
        elif action == "shutdown":
            self.emit("shutdown")
            self.root.destroy()
        else:
            raise ValueError("unknown command")

    def _drain_commands(self) -> None:
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                break
            try:
                self.handle(command)
            except (tk.TclError, ValueError) as exc:
                self._records.put({
                    "schema_version": 1, "kind": "command_error", "run_nonce": self.run_nonce,
                    "reason": type(exc).__name__,
                })
        if self.root.winfo_exists():
            self.root.after(20, self._drain_commands)


def _read_commands(target: ControlledTarget) -> None:
    for line in sys.stdin:
        try:
            command = json.loads(line)
            if not isinstance(command, dict):
                continue
        except json.JSONDecodeError:
            continue
        target.commands.put(command)
    target.commands.put({"command": "shutdown"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-text", required=True)
    parser.add_argument("--run-nonce", required=True)
    args = parser.parse_args()
    if not args.run_nonce or any(char.isspace() for char in args.run_nonce):
        parser.error("run nonce must be a nonempty token")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        root = tk.Tk()
        root.title("ClipAI controlled paste target")
        target = ControlledTarget(root, output=output, expected_text=args.expected_text, run_nonce=args.run_nonce)
        root.update_idletasks()
        target.emit("ready")
        threading.Thread(target=_read_commands, args=(target,), daemon=True).start()
        root.mainloop()
        target.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
