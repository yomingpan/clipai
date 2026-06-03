from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

from clipai.platform.hotkey import LONG_PRESS_SEC, _HotkeyDispatcher


@dataclass
class FakeTimer:
    interval: float
    callback: Callable[[], None]
    daemon: bool = False
    started: bool = False
    cancelled: bool = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()


class HotkeyDriver:
    def __init__(self, hotkeys: list[tuple[str, set[str]]]) -> None:
        self.events: list[tuple[str, str]] = []
        self.timers: list[FakeTimer] = []
        self.dispatcher = _HotkeyDispatcher(
            hotkeys,
            lambda action_id, press_type: self.events.append((action_id, press_type)),
            long_press_sec=LONG_PRESS_SEC,
            timer_factory=self._make_timer,
        )

    def _make_timer(self, interval: float, callback: Callable[[], None]) -> FakeTimer:
        timer = FakeTimer(interval, callback)
        self.timers.append(timer)
        return timer

    def press(self, token: str) -> None:
        self.dispatcher.on_press(_key(token))

    def release(self, token: str) -> None:
        self.dispatcher.on_release(_key(token))

    def press_all(self, *tokens: str) -> None:
        for token in tokens:
            self.press(token)

    def release_all(self, *tokens: str) -> None:
        for token in tokens:
            self.release(token)

    def fire_long_timer(self, index: int = 0) -> None:
        self.timers[index].fire()


def _key(token: str):
    lowered = token.lower()
    if lowered in {"ctrl", "alt", "shift"}:
        return SimpleNamespace(name=f"{lowered}_l")
    if len(lowered) == 1 and lowered.isdigit():
        return SimpleNamespace(vk=ord(lowered))
    if len(lowered) == 1 and lowered.isalpha():
        return SimpleNamespace(vk=ord(lowered.upper()))
    return SimpleNamespace(name=lowered)
