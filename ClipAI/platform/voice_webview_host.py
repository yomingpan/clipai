from __future__ import annotations

import json
import sys
import threading
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from ClipAI.platform.browser_speech import VOICE_PROTOCOL_VERSION


def voice_webview_profile_dir(local_app_data: Path) -> Path:
    """Return the app-owned WebView profile that retains microphone consent."""
    profile = local_app_data / "ClipAI" / "VoiceWebView"
    profile.mkdir(parents=True, exist_ok=True)
    return profile


class _Api:
    def __init__(self, bridge_ready: threading.Event) -> None:
        # pywebview exposes every public attribute of ``js_api`` to JavaScript.
        # Keeping the native Window private prevents it from recursively walking
        # the complete pywebview object graph while it is building that bridge.
        self._window: Any | None = None
        self._bridge_ready = bridge_ready

    def emit(self, payload: dict[str, object]) -> None:
        if payload.get("kind") == "bridge_ready":
            self._bridge_ready.set()
            return
        sys.stdout.write(json.dumps({"version": VOICE_PROTOCOL_VERSION, **payload}, ensure_ascii=True) + "\n")
        sys.stdout.flush()

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()


def main(*, test_page: Path | None = None, profile_root: Path | None = None) -> None:
    import webview

    bridge_ready = threading.Event()
    api = _Api(bridge_ready)
    loaded = threading.Event()
    html = (test_page or Path(__file__).with_name("voice_webview_host.html")).resolve()
    window = webview.create_window(
        "ClipAI Voice Engine",
        url=html.as_uri(),
        js_api=api,
        hidden=True,
        focus=False,
        width=420,
        height=180,
    )
    api._window = window

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
            if name in {"prepare", "start"} and test_page is None:
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
        def wait_for_bridge() -> None:
            if not bridge_ready.wait(10):
                return
            loaded.set()
            if test_page is not None:
                api.emit({"kind": "test_loaded"})

        threading.Thread(target=wait_for_bridge, daemon=True).start()

    window.events.loaded += on_loaded
    threading.Thread(target=read_commands, daemon=True).start()
    # Keep a profile owned only by ClipAI so the browser remembers the user's
    # microphone decision. The profile contains permission metadata, not any
    # microphone recording or recognition transcript managed by this host.
    webview.start(
        gui="edgechromium",
        private_mode=False,
        storage_path=str(voice_webview_profile_dir(profile_root or Path.cwd())),
    )


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
    parser.add_argument("--profile-root", type=Path)
    arguments = parser.parse_args()
    main(test_page=arguments.test_page, profile_root=arguments.profile_root)
