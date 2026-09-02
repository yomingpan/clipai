from __future__ import annotations

from collections.abc import Callable
import ctypes
import time
from typing import TypeAlias

from ClipAI.core.errors import CancelledError
from ClipAI.core.models import (
    ExternalWindowActivationOutcome,
    ExternalWindowActivationState,
    ExternalWindowRef,
    PasteTarget,
)
from ClipAI.core.state import CancellationToken
from ClipAI.platform.keyboard_state import MODIFIER_KEYS, windows_modifier_is_pressed
from ClipAI.platform.window_activation import activate_top_level_window
from ClipAI.platform.win32_api import configure_win32_api


_MESSAGES = {
    "modifiers_held": "Release Ctrl and Alt, then try again.",
    "target_gone": "The original window is no longer available.",
    "target_refused_focus": "The original window refused focus.",
    "target_focus_timeout": "The original window did not receive focus in time.",
    "target_changed": "The original window changed before input capture.",
}

ExternalWindowTarget: TypeAlias = ExternalWindowRef | PasteTarget


class SystemExternalWindowActivator:
    def __init__(
        self,
        *,
        modifier_is_pressed: Callable[[str], bool | None] = windows_modifier_is_pressed,
        modifier_release_timeout_sec: float = 1.0,
        target_activation_timeout_sec: float = 0.5,
        target_confirmation_timeout_sec: float | None = None,
        poll_sec: float = 0.02,
        wait: Callable[[float], None] = time.sleep,
        target_is_valid: Callable[[ExternalWindowTarget], bool] | None = None,
        activate_target: Callable[[ExternalWindowTarget], bool] | None = None,
        target_is_foreground: Callable[[ExternalWindowTarget], bool] | None = None,
    ) -> None:
        self._modifier_is_pressed = modifier_is_pressed
        self._modifier_release_timeout_sec = modifier_release_timeout_sec
        self._target_activation_timeout_sec = target_activation_timeout_sec
        self._target_confirmation_timeout_sec = (
            target_activation_timeout_sec
            if target_confirmation_timeout_sec is None
            else target_confirmation_timeout_sec
        )
        self._poll_sec = poll_sec
        self._wait = wait
        self._target_is_valid = target_is_valid or windows_target_is_valid
        self._activate_target = activate_target or activate_windows_target
        self._target_is_foreground = target_is_foreground or windows_target_is_foreground

    def activate(
        self,
        target: ExternalWindowTarget,
        cancellation: CancellationToken,
    ) -> ExternalWindowActivationOutcome:
        modifier_deadline = time.monotonic() + self._modifier_release_timeout_sec
        while any(self._modifier_is_pressed(modifier) is True for modifier in MODIFIER_KEYS):
            _raise_if_cancelled(cancellation)
            if time.monotonic() >= modifier_deadline:
                return _outcome("modifiers_held")
            self._wait(self._poll_sec)
        _raise_if_cancelled(cancellation)
        if not self._target_is_valid(target):
            return _outcome("target_gone")
        activation_deadline = time.monotonic() + self._target_activation_timeout_sec
        request_was_accepted = False
        while True:
            _raise_if_cancelled(cancellation)
            request_was_accepted = self._activate_target(target) or request_was_accepted
            if self._target_is_foreground(target):
                break
            if time.monotonic() >= activation_deadline:
                return _outcome(
                    "target_focus_timeout"
                    if request_was_accepted
                    else "target_refused_focus"
                )
            self._wait(self._poll_sec)
            _raise_if_cancelled(cancellation)
            if time.monotonic() >= activation_deadline:
                return _outcome(
                    "target_focus_timeout"
                    if request_was_accepted
                    else "target_refused_focus"
                )
            if not self._target_is_valid(target):
                return _outcome("target_changed")
        _raise_if_cancelled(cancellation)
        confirmation = self.confirm(target, cancellation)
        _raise_if_cancelled(cancellation)
        return confirmation

    def confirm(
        self,
        target: ExternalWindowTarget,
        cancellation: CancellationToken | None = None,
    ) -> ExternalWindowActivationOutcome:
        deadline = time.monotonic() + self._target_confirmation_timeout_sec
        while True:
            _raise_if_cancelled(cancellation)
            if not self._target_is_valid(target):
                return _outcome("target_changed")
            if self._target_is_foreground(target):
                return ExternalWindowActivationOutcome("activated")
            if time.monotonic() >= deadline:
                return _outcome("target_changed")
            self._wait(self._poll_sec)


def windows_target_is_valid(target: ExternalWindowTarget) -> bool:
    handle = _window_handle(target)
    if handle is None:
        return False
    user32 = ctypes.windll.user32
    process_id = ctypes.c_ulong()
    configure_win32_api(user32, ctypes.windll.kernel32)
    try:
        return bool(
            user32.IsWindow(handle)
            and user32.IsWindowVisible(handle)
            and user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            and process_id.value == target.process_id
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def activate_windows_target(target: ExternalWindowTarget) -> bool:
    handle = _window_handle(target)
    if handle is None:
        return False
    try:
        return activate_top_level_window(
            handle,
            user32=ctypes.windll.user32,
            kernel32=ctypes.windll.kernel32,
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def windows_target_is_foreground(target: ExternalWindowTarget) -> bool:
    handle = _window_handle(target)
    if handle is None:
        return False
    try:
        user32 = ctypes.windll.user32
        configure_win32_api(user32, ctypes.windll.kernel32)
        return int(user32.GetForegroundWindow()) == handle
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _window_handle(target: ExternalWindowTarget) -> int | None:
    prefix = "hwnd:"
    if not target.window_token.startswith(prefix):
        return None
    try:
        return int(target.window_token[len(prefix):], 16)
    except ValueError:
        return None


def _raise_if_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation is not None and cancellation.is_cancelled:
        raise CancelledError("External window activation was cancelled.")


def _outcome(state: ExternalWindowActivationState) -> ExternalWindowActivationOutcome:
    return ExternalWindowActivationOutcome(state, _MESSAGES[state])
