from __future__ import annotations

from collections.abc import Callable
import ctypes
import time

from ClipAI.core.errors import CancelledError
from ClipAI.core.models import PasteDispatchReceipt, PasteTarget
from ClipAI.core.state import CancellationToken
from ClipAI.platform.keyboard_state import MODIFIER_KEYS, windows_modifier_is_pressed


class SystemKeyboardOutput:
    def __init__(
        self,
        *,
        modifier_is_pressed: Callable[[str], bool | None] = windows_modifier_is_pressed,
        modifier_release_timeout_sec: float = 1.0,
        target_activation_timeout_sec: float = 0.5,
        poll_sec: float = 0.02,
        wait: Callable[[float], None] = time.sleep,
        paste_shortcut: Callable[[], None] | None = None,
        target_is_valid: Callable[[PasteTarget], bool] | None = None,
        activate_target: Callable[[PasteTarget], bool] | None = None,
        target_is_foreground: Callable[[PasteTarget], bool] | None = None,
    ) -> None:
        self._modifier_is_pressed = modifier_is_pressed
        self._modifier_release_timeout_sec = modifier_release_timeout_sec
        self._target_activation_timeout_sec = target_activation_timeout_sec
        self._poll_sec = poll_sec
        self._wait = wait
        self._paste_shortcut = paste_shortcut or _send_paste_shortcut
        self._target_is_valid = target_is_valid or _windows_target_is_valid
        self._activate_target = activate_target or _activate_windows_target
        self._target_is_foreground = target_is_foreground or _windows_target_is_foreground

    def dispatch(self, target: PasteTarget, cancellation: CancellationToken) -> PasteDispatchReceipt:
        deadline = time.monotonic() + self._modifier_release_timeout_sec
        while any(self._modifier_is_pressed(modifier) is True for modifier in MODIFIER_KEYS):
            _raise_if_cancelled(cancellation)
            if time.monotonic() >= deadline:
                raise RuntimeError("Keyboard modifiers were not released in time.")
            self._wait(self._poll_sec)
        _raise_if_cancelled(cancellation)
        if not self._target_is_valid(target):
            raise RuntimeError("找不到貼上目標。請先點選要貼入的視窗，再回到 ClipAI。")
        if not self._activate_target(target) and not self._target_is_foreground(target):
            raise RuntimeError("找不到貼上目標。請先點選要貼入的視窗，再回到 ClipAI。")
        activation_deadline = time.monotonic() + self._target_activation_timeout_sec
        while not self._target_is_foreground(target):
            _raise_if_cancelled(cancellation)
            if time.monotonic() >= activation_deadline:
                raise RuntimeError("找不到貼上目標。請先點選要貼入的視窗，再回到 ClipAI。")
            self._wait(self._poll_sec)
        _raise_if_cancelled(cancellation)
        if not self._target_is_valid(target) or not self._target_is_foreground(target):
            raise RuntimeError("Paste target changed before dispatch.")
        _raise_if_cancelled(cancellation)
        try:
            self._paste_shortcut()
        except Exception:
            return PasteDispatchReceipt(
                "dispatched_unconfirmed",
                "Input injection returned an error after the Paste Dispatch point.",
            )
        return PasteDispatchReceipt("dispatched_unconfirmed")


def _send_paste_shortcut() -> None:
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("v")
        keyboard.release("v")


def _raise_if_cancelled(cancellation: CancellationToken) -> None:
    if cancellation.is_cancelled:
        raise CancelledError("Paste was cancelled before dispatch.")


def _windows_target_is_valid(target: PasteTarget) -> bool:
    handle = _window_handle(target)
    if handle is None:
        return False
    user32 = ctypes.windll.user32
    process_id = ctypes.c_ulong()
    try:
        return bool(
            user32.IsWindow(handle)
            and user32.IsWindowVisible(handle)
            and user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            and process_id.value == target.process_id
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _activate_windows_target(target: PasteTarget) -> bool:
    handle = _window_handle(target)
    if handle is None:
        return False
    try:
        return bool(ctypes.windll.user32.SetForegroundWindow(handle))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _windows_target_is_foreground(target: PasteTarget) -> bool:
    handle = _window_handle(target)
    if handle is None:
        return False
    try:
        return int(ctypes.windll.user32.GetForegroundWindow()) == handle
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _window_handle(target: PasteTarget) -> int | None:
    prefix = "hwnd:"
    if not target.window_token.startswith(prefix):
        return None
    try:
        return int(target.window_token[len(prefix):], 16)
    except ValueError:
        return None
