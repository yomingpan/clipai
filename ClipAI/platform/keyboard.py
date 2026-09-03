from __future__ import annotations

from collections.abc import Callable
import logging
import time

from ClipAI.core.errors import PASTE_FAILURE_MESSAGES, PasteFailure
from ClipAI.core.models import ExternalWindowActivationState, PasteDispatchReceipt, PasteTarget
from ClipAI.core.state import CancellationToken
from ClipAI.platform.external_window import SystemExternalWindowActivator, diagnostic_foreground_context
from ClipAI.platform.keyboard_state import windows_modifier_is_pressed


logger = logging.getLogger("clipai.keyboard_paste")


class SystemKeyboardOutput:
    def __init__(
        self,
        *,
        modifier_is_pressed: Callable[[str], bool | None] = windows_modifier_is_pressed,
        modifier_release_timeout_sec: float = 1.0,
        target_activation_timeout_sec: float = 0.5,
        paste_settle_sec: float = 0.25,
        poll_sec: float = 0.02,
        wait: Callable[[float], None] = time.sleep,
        paste_shortcut: Callable[[], None] | None = None,
        target_is_valid: Callable[[PasteTarget], bool] | None = None,
        activate_target: Callable[[PasteTarget], bool] | None = None,
        target_is_foreground: Callable[[PasteTarget], bool] | None = None,
    ) -> None:
        self._paste_settle_sec = paste_settle_sec
        self._wait = wait
        self._paste_shortcut = paste_shortcut or _send_paste_shortcut
        self._external_activation = SystemExternalWindowActivator(
            modifier_is_pressed=modifier_is_pressed,
            modifier_release_timeout_sec=modifier_release_timeout_sec,
            target_activation_timeout_sec=target_activation_timeout_sec,
            poll_sec=poll_sec,
            wait=wait,
            target_is_valid=target_is_valid,
            activate_target=activate_target,
            target_is_foreground=target_is_foreground,
        )

    def dispatch(
        self,
        operation_id: str,
        target: PasteTarget,
        cancellation: CancellationToken,
    ) -> PasteDispatchReceipt:
        started_at = time.monotonic()
        activation = self._external_activation.activate(target, cancellation)
        log = logger.info if activation.activated else logger.warning
        log(
            "Keyboard paste trace stage=activation operation_id=%s state=%s "
            "target_window=%s target_process_id=%s",
            operation_id,
            activation.state,
            target.window_token,
            target.process_id,
        )
        if not activation.activated:
            raise _paste_failure_for_activation(activation.state)
        detail = ""
        _log_foreground("shortcut_started", operation_id, target, started_at)
        try:
            self._paste_shortcut()
        except Exception:
            detail = "Input injection returned an error after the Paste Dispatch point."
        _log_foreground(
            "shortcut_returned",
            operation_id,
            target,
            started_at,
            injection_error=bool(detail),
        )
        # Input injection can return before the target consumes the clipboard.
        # Keep the transient payload available without claiming confirmation.
        if self._paste_settle_sec > 0:
            self._wait(self._paste_settle_sec)
        _log_foreground("settled", operation_id, target, started_at)
        return PasteDispatchReceipt("dispatched_unconfirmed", detail)


def _log_foreground(
    stage: str,
    operation_id: str,
    target: PasteTarget,
    started_at: float,
    *,
    injection_error: bool = False,
) -> None:
    foreground_window, foreground_process_id, foreground_owner = (
        diagnostic_foreground_context(target)
    )
    logger.info(
        "Keyboard paste trace stage=%s operation_id=%s target_window=%s "
        "target_process_id=%s foreground_window=%s foreground_process_id=%s "
        "foreground_owner=%s injection_error=%s elapsed_ms=%s",
        stage,
        operation_id,
        target.window_token,
        target.process_id,
        foreground_window,
        foreground_process_id,
        foreground_owner,
        injection_error,
        max(0, round((time.monotonic() - started_at) * 1000)),
    )


def _send_paste_shortcut() -> None:
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("v")
        keyboard.release("v")


def _paste_failure_for_activation(state: ExternalWindowActivationState) -> PasteFailure:
    if state == "modifiers_held":
        return PasteFailure("modifiers_held", PASTE_FAILURE_MESSAGES["modifiers_held"])
    if state == "target_gone":
        return PasteFailure("target_gone", PASTE_FAILURE_MESSAGES["target_gone"])
    if state == "target_refused_focus":
        return PasteFailure(
            "target_refused_focus",
            PASTE_FAILURE_MESSAGES["target_refused_focus"],
        )
    if state == "target_focus_timeout":
        return PasteFailure(
            "target_focus_timeout",
            PASTE_FAILURE_MESSAGES["target_focus_timeout"],
        )
    if state == "target_changed":
        return PasteFailure("target_changed", PASTE_FAILURE_MESSAGES["target_changed"])
    raise RuntimeError(f"unexpected external activation state: {state}")
