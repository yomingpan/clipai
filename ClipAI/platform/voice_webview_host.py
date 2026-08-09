from __future__ import annotations

import json
import sys
import threading
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from ClipAI.platform.browser_speech import VOICE_PROTOCOL_VERSION


class _Api:
    def __init__(self) -> None:
        self.window: Any | None = None

    def emit(self, payload: dict[str, object]) -> None:
        sys.stdout.write(json.dumps({"version": VOICE_PROTOCOL_VERSION, **payload}, ensure_ascii=True) + "\n")
        sys.stdout.flush()

    def hide(self) -> None:
        if self.window is not None:
            self.window.hide()


def main(*, test_page: Path | None = None) -> None:
    import webview

    api = _Api()
    loaded = threading.Event()
    html = (test_page or Path(__file__).with_name("voice_webview_host.html")).resolve()
    window = webview.create_window(
        "ClipAI Voice Engine",
        url=str(html),
        js_api=api,
        hidden=True,
        focus=False,
        width=420,
        height=180,
    )
    api.window = window

    def read_commands() -> None:
        for line in sys.stdin:
            try:
                command = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(command, dict) or command.get("version") != VOICE_PROTOCOL_VERSION:
                continue
            name = str(command.get("command") or "")
            if name == "shutdown":
                if loaded.wait(3):
                    try:
                        window.evaluate_js("window.clipaiVoice.shutdown()")
                        window.destroy()
                    except Exception:
                        pass
                return
            if name not in {"prepare", "start", "stop", "cancel"} or not loaded.wait(10):
                _emit_command_failure(api, command, "initialization_failed")
                continue
            if name == "prepare" and test_page is None:
                try:
                    window.show()
                    window.restore()
                    window.focus()
                except Exception:
                    pass
            try:
                window.evaluate_js(f"window.clipaiVoice.command({json.dumps(command, ensure_ascii=True)})")
            except Exception:
                _emit_command_failure(api, command, "initialization_failed")

    def on_loaded() -> None:
        loaded.set()
        if test_page is not None:
            api.emit({"kind": "test_loaded"})

    window.events.loaded += on_loaded
    threading.Thread(target=read_commands, daemon=True).start()
    webview.start(gui="edgechromium", private_mode=True)


def _emit_command_failure(api: _Api, command: dict[str, object], failure: str) -> None:
    if command.get("command") == "prepare":
        api.emit({"kind": "setup_failed", "setup_id": str(command.get("setup_id") or ""), "failure": failure})
    else:
        capture_id = str(command.get("capture_id") or "")
        if capture_id:
            api.emit({"kind": "failed", "capture_id": capture_id, "failure": failure})
            api.emit({"kind": "ended", "capture_id": capture_id})


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--test-page", type=Path)
    main(test_page=parser.parse_args().test_page)
