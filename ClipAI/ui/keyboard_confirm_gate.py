"""Toolkit-neutral admission for an intentional press/release confirmation."""

from collections.abc import Callable
import time


ENTER_SETTLE_SECONDS = .3
LOCK_BITS = 0x0002 | 0x0008 | 0x0010


class KeyboardConfirmGate:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 key_down_reader: Callable[[], bool | None] = lambda: None) -> None:
        self._clock = clock
        self._key_down_reader = key_down_reader
        self._focused = False
        self._ready_at = float("inf")
        self._down = False
        self._candidate = False

    def focus_changed(self, focused: bool) -> None:
        if focused != self._focused:
            self._focused = focused
            if focused:
                held = self._key_down_reader()
                if held is not None:
                    self._down = held
            self.restart()

    def restart(self) -> None:
        self._candidate = False
        self._ready_at = self._clock()+ENTER_SETTLE_SECONDS if self._focused else float("inf")

    def press(self, *, state: int = 0) -> None:
        self._candidate = not self._down and self._focused and self._clock() >= self._ready_at and state & ~LOCK_BITS == 0
        self._down = True

    def release(self, *, state: int = 0) -> bool:
        accepted = self._down and self._candidate and self._focused and state & ~LOCK_BITS == 0
        self._down = self._candidate = False
        return accepted
