"""Check the local pywebview/WebView2 bridge without microphone or ClipAI state."""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import threading
from pathlib import Path


class _BridgeApi:
    def __init__(self, ready: threading.Event) -> None:
        self._ready = ready

    def ping(self) -> None:
        self._ready.set()


class _StartupErrorCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.webview2_failed = False

    def emit(self, record: logging.LogRecord) -> None:
        if "WebView2 initialization failed" in record.getMessage():
            self.webview2_failed = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visible", action="store_true", help="show the test window without requesting focus")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, help="write the content-free result as JSON")
    parser.add_argument("--profile-root", type=Path, help="use an isolated persistent WebView2 data folder")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    import webview

    page_loaded = threading.Event()
    bridge_ready = threading.Event()
    script_finished = threading.Event()
    script_state = ["not_started"]
    window = webview.create_window(
        "ClipAI bridge probe",
        html=(
            "<script>window.addEventListener('pywebviewready', "
            "() => window.pywebview.api.ping(), {once: true});</script>"
        ),
        js_api=_BridgeApi(bridge_ready),
        hidden=not args.visible,
        focus=False,
    )
    window.events.loaded += page_loaded.set

    def check_script() -> None:
        if not page_loaded.wait(args.timeout):
            return
        script_state[0] = "unresponsive"
        try:
            value = window.evaluate_js("JSON.stringify({answer: 2})", raw=True)
            script_state[0] = "returned_expected" if value == {"answer": 2} else f"returned_{type(value).__name__}_{value!r}"
        except Exception as exc:
            script_state[0] = f"error_{type(exc).__name__}"
        finally:
            script_finished.set()

    threading.Thread(target=check_script, daemon=True).start()

    def close() -> None:
        try:
            window.destroy()
        except Exception:
            pass

    timeout = threading.Timer(args.timeout, close)
    timeout.daemon = True
    timeout.start()
    error_type = ""
    profile = None
    if args.profile_root is None:
        profile = tempfile.TemporaryDirectory(prefix="ClipAI-webview-probe-", ignore_cleanup_errors=True)
        storage_path = Path(profile.name)
    else:
        storage_path = args.profile_root.resolve()
        storage_path.mkdir(parents=True, exist_ok=True)
    startup_errors = _StartupErrorCapture()
    logging.getLogger("pywebview").addHandler(startup_errors)
    try:
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(storage_path))
    except Exception as exc:
        error_type = type(exc).__name__
    finally:
        timeout.cancel()
        logging.getLogger("pywebview").removeHandler(startup_errors)
        if profile is not None:
            profile.cleanup()
    if startup_errors.webview2_failed and not error_type:
        error_type = "webview2_initialization_failed"

    result = {
        "page_loaded": page_loaded.is_set(),
        "bridge_ready": bridge_ready.is_set(),
        "script_eval": script_state[0] if script_finished.is_set() else "unresponsive" if page_loaded.is_set() else "not_started",
        "error_type": error_type,
    }
    report = json.dumps(result, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if result["bridge_ready"] and not error_type else 1


if __name__ == "__main__":
    raise SystemExit(main())
