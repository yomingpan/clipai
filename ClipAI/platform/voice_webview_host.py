from __future__ import annotations

import json
import sys
import threading
import traceback
from argparse import ArgumentParser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ClipAI.platform.browser_speech import VOICE_PROTOCOL_VERSION
from ClipAI.platform.voice_webview_profile import voice_webview_profile_dir


def is_explicit_voice_microphone_request(command: str) -> bool:
    """Only explicit setup or admitted Push-to-Talk capture may access the microphone."""
    return command in {"prepare", "start"}


def allow_microphone_permission(
    request: Any,
    *,
    microphone_kind: object,
    allow_state: object,
    activate_host: Callable[[], None] | None = None,
) -> None:
    """Resolve and persist only WebView microphone permission requests."""
    if request.PermissionKind != microphone_kind:
        return
    if activate_host is not None:
        try:
            # A newly created, fully hidden WebView2 cannot complete its first
            # getUserMedia permission handshake. Show only for that real
            # permission request; do not restore or focus the host.
            activate_host()
        except Exception:
            traceback.print_exc(file=sys.stderr)
    request.State = allow_state
    request.SavesInProfile = True
    request.Handled = True


def realise_voice_host_invisibly(window: Any, *, user32: Any | None = None) -> bool:
    """Realise the WinForms WebView host while keeping every frame transparent."""
    if user32 is None:
        if sys.platform != "win32":
            return False
        import ctypes

        user32 = ctypes.windll.user32
    try:
        native = window.native

        def realise() -> None:
            native.Opacity = 0.0
            handle = _native_handle_value(native.Handle)
            gwl_exstyle = -20
            ws_ex_toolwindow = 0x00000080
            ws_ex_appwindow = 0x00040000
            ws_ex_noactivate = 0x08000000
            style = int(user32.GetWindowLongW(handle, gwl_exstyle))
            user32.SetWindowLongW(
                handle,
                gwl_exstyle,
                (style | ws_ex_toolwindow | ws_ex_noactivate) & ~ws_ex_appwindow,
            )
            native.Show()

        _run_on_winforms_ui_thread(native, realise)
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        traceback.print_exc(file=sys.stderr)
        return False


def _native_handle_value(handle: Any) -> int:
    """Convert pythonnet's System.IntPtr without relying on int(IntPtr)."""
    to_int64 = getattr(handle, "ToInt64", None)
    if callable(to_int64):
        return int(to_int64())
    return int(handle)


def _run_on_winforms_ui_thread(native: Any, action: Callable[[], None]) -> None:
    """Marshal only when required; invoking from the UI thread can deadlock."""
    if not bool(getattr(native, "InvokeRequired", False)):
        action()
        return
    try:
        from System import Action

        callback = Action(action)
    except ImportError:
        callback = action
    native.Invoke(callback)


def _attach_microphone_permission_handler(
    window: Any,
    retained_handlers: list[Any],
    permission_command: list[str],
) -> None:
    """Attach the WebView2 permission policy on its Windows UI thread."""
    from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind, CoreWebView2PermissionState
    def handle_permission(_sender: object, request: Any) -> None:
        if request.PermissionKind != CoreWebView2PermissionKind.Microphone:
            return
        command = permission_command[0]
        if not is_explicit_voice_microphone_request(command):
            request.State = CoreWebView2PermissionState.Deny
            request.Handled = True
            return
        allow_microphone_permission(
            request,
            microphone_kind=CoreWebView2PermissionKind.Microphone,
            allow_state=CoreWebView2PermissionState.Allow,
            activate_host=lambda: realise_voice_host_invisibly(window),
        )

    def attach() -> None:
        core_webview = window.native.browser.webview.CoreWebView2
        core_webview.PermissionRequested += handle_permission

    _run_on_winforms_ui_thread(window.native, attach)
    retained_handlers.append(handle_permission)


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


def _dispatch_host_command(
    window: Any,
    api: _Api,
    command: dict[str, object],
    *,
    loaded: threading.Event,
    permission_command: list[str] | None = None,
    capture_surface: Callable[[Any], bool] | None = realise_voice_host_invisibly,
) -> bool:
    """Forward one validated transport command to the voice page.

    Returns ``False`` only when the host should exit after a shutdown request.
    """
    name = str(command.get("command") or "")
    if name == "shutdown":
        if loaded.wait(3):
            try:
                window.evaluate_js("window.clipaiVoice.shutdown()")
                window.destroy()
            except Exception:
                pass
        return False
    if name not in {"prepare", "start", "stop", "cancel"} or not loaded.wait(10):
        _emit_command_failure(api, command, "initialization_failed")
        return True
    if permission_command is not None and name in {"prepare", "start"}:
        permission_command[0] = name
    if name in {"prepare", "start"} and capture_surface is not None:
        try:
            # Web Speech requires its WebView host to be available when capture
            # begins. Request a non-activating native surface first, then let
            # pywebview record its own visible lifecycle transition.
            realised = capture_surface(window)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            realised = False
        if not realised:
            _emit_command_failure(api, command, "initialization_failed")
            return True
    # This is an intentionally hidden host. It has an explicit WebView2
    # microphone-permission policy and a persistent app-owned profile, so
    # preparing or starting capture must not steal focus from the user's work.
    try:
        window.evaluate_js(f"window.clipaiVoice.command({json.dumps(command, ensure_ascii=True)})")
    except Exception:
        _emit_command_failure(api, command, "initialization_failed")
    return True


def main(*, test_page: Path | None = None, profile_root: Path | None = None) -> None:
    import webview

    bridge_ready = threading.Event()
    api = _Api(bridge_ready)
    loaded = threading.Event()
    retained_permission_handlers: list[Any] = []
    permission_command = [""]
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
            if not _dispatch_host_command(
                window,
                api,
                command,
                loaded=loaded,
                permission_command=permission_command,
            ):
                return

    def on_loaded() -> None:
        try:
            _attach_microphone_permission_handler(
                window,
                retained_permission_handlers,
                permission_command,
            )
        except Exception:
            return

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
