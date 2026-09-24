"""Single owner of capture-scoped timers and their typed observations."""

from __future__ import annotations

import math
from collections.abc import Callable

from ClipAI.core.commands import (
    VoiceCaptureCountdownTick, VoiceCaptureCountdownTickForCapture,
    VoiceCaptureTimeout, VoiceCaptureWatchdogExpired,
    VoiceFinalizeWatchdogExpired, VoiceSilenceWatchdogExpired,
)
from ClipAI.core.models import ShortcutPressId
from ClipAI.core.voice import VoiceCaptureId, VoiceCapturePhase, VoiceProjection


class VoiceCaptureTiming:
    def __init__(
        self,
        schedule: Callable[[float, Callable[[], None]], object],
        clock: Callable[[], float],
        dispatch: Callable[[object], None],
        press_id_for_capture: Callable[[VoiceCaptureId], ShortcutPressId | None],
    ) -> None:
        self._schedule = schedule
        self._clock = clock
        self._dispatch = dispatch
        self._press_id_for_capture = press_id_for_capture
        self._capture_id: VoiceCaptureId | None = None
        self._deadline: float | None = None
        self._timers: dict[str, object] = {}
        self._phase: VoiceCapturePhase | None = None

    def observe(self, projection: VoiceProjection) -> None:
        capture_id = projection.capture_id
        if capture_id is None:
            self.cancel_all()
            return
        if capture_id != self._capture_id:
            self.cancel_all()
            self._capture_id = capture_id
        phase = projection.capture_phase
        if phase in {VoiceCapturePhase.STOP_REQUESTED, VoiceCapturePhase.FINALIZING, VoiceCapturePhase.CANCEL_REQUESTED}:
            self._cancel("deadline")
            self._cancel("countdown")
            self._cancel("silence")
            self._deadline = None
            if "finalize" not in self._timers:
                self._timers["finalize"] = self._schedule(
                    6.0, lambda: self._dispatch_if_current(capture_id, VoiceFinalizeWatchdogExpired(capture_id))
                )
        elif phase is VoiceCapturePhase.LISTENING:
            self._cancel("finalize")
            if self._deadline is None:
                self._deadline = self._clock() + 120.0
                self._timers["deadline"] = self._schedule(120.0, lambda: self._expire(capture_id))
                self._schedule_countdown(capture_id)
            if self._phase is not VoiceCapturePhase.LISTENING and "silence" not in self._timers:
                self._timers["silence"] = self._schedule(
                    2.0, lambda: self._dispatch_if_current(capture_id, VoiceSilenceWatchdogExpired(capture_id))
                )
        self._phase = phase

    def cancel_all(self) -> None:
        for kind in tuple(self._timers):
            self._cancel(kind)
        self._capture_id = None
        self._deadline = None
        self._phase = None

    def _schedule_countdown(self, capture_id: VoiceCaptureId) -> None:
        if self._deadline is None or "countdown" in self._timers:
            return
        remaining = self._deadline - self._clock()
        if remaining > 0:
            self._timers["countdown"] = self._schedule(min(1.0, remaining), lambda: self._tick(capture_id))

    def _tick(self, capture_id: VoiceCaptureId) -> None:
        if capture_id != self._capture_id or self._deadline is None:
            return
        self._timers.pop("countdown", None)
        remaining = max(0, math.ceil(self._deadline - self._clock()))
        press_id = self._press_id_for_capture(capture_id)
        self._dispatch(
            VoiceCaptureCountdownTick(press_id, remaining) if press_id is not None
            else VoiceCaptureCountdownTickForCapture(capture_id, remaining)
        )
        self._schedule_countdown(capture_id)

    def _expire(self, capture_id: VoiceCaptureId) -> None:
        if capture_id != self._capture_id or self._deadline is None:
            return
        remaining = self._deadline - self._clock()
        if remaining > 0:
            self._timers["deadline"] = self._schedule(remaining, lambda: self._expire(capture_id))
            return
        press_id = self._press_id_for_capture(capture_id)
        self._dispatch(VoiceCaptureWatchdogExpired(press_id) if press_id is not None else VoiceCaptureTimeout(capture_id))

    def _dispatch_if_current(self, capture_id: VoiceCaptureId, command: object) -> None:
        if capture_id == self._capture_id:
            if isinstance(command, VoiceSilenceWatchdogExpired):
                self._timers.pop("silence", None)
            self._dispatch(command)

    def _cancel(self, kind: str) -> None:
        timer = self._timers.pop(kind, None)
        if timer is not None and hasattr(timer, "cancel"):
            timer.cancel()
