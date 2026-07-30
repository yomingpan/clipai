from __future__ import annotations

from collections.abc import Callable
import threading

from ClipAI.core.commands import AppCommand, ShortcutTriggered, StartAction
from ClipAI.services.shortcut_catalog import ShortcutCatalog


class ShortcutSequenceCoordinator:
    """Owns composition policy independently of raw keyboard state."""

    def __init__(
        self,
        shortcuts: ShortcutCatalog,
        *,
        timeout_sec: float = 1.0,
        schedule: Callable[[float, Callable[[], None]], object] | None = None,
        on_waiting: Callable[[], None] = lambda: None,
        on_error: Callable[[str, str], None] = lambda _message, _suggestion: None,
        on_cancel_active: Callable[[], None] = lambda: None,
    ) -> None:
        self._shortcuts = shortcuts
        self._timeout_sec = timeout_sec
        self._schedule = schedule or self._schedule_timer
        self._on_waiting = on_waiting
        self._on_error = on_error
        self._on_cancel_active = on_cancel_active
        self._armed_shortcut: str | None = None
        self._waiting = False
        self._timer: object | None = None
        self._generation = 0

    @staticmethod
    def _schedule_timer(delay: float, callback: Callable[[], None]) -> threading.Timer:
        timer = threading.Timer(delay, callback)
        timer.daemon = True
        timer.start()
        return timer

    def resolve(self, trigger: ShortcutTriggered) -> AppCommand | None:
        if trigger.press_type == "cancel":
            self.cancel()
            return None
        if trigger.press_type == "invalid":
            if self._waiting:
                self.cancel()
                self._on_error("Invalid shortcut sequence.", "Choose an action shortcut after Ctrl+Alt+Q.")
            return None
        definition = self._shortcuts.definition(trigger.shortcut_id)
        is_composer = definition.command == "speak_selection_or_clipboard"
        if is_composer and trigger.press_type == "long":
            self.cancel()
            self._on_cancel_active()
            self._armed_shortcut = trigger.shortcut_id
            self._waiting = True
            self._on_waiting()
            self._start_timeout()
            return None
        if is_composer and trigger.press_type == "long_release" and self._armed_shortcut == trigger.shortcut_id:
            # The sequence was already armed when the long-press threshold was
            # reached. Releasing Q must not change or restart that lifecycle.
            return None
        if trigger.press_type == "long_release":
            return None
        if self._waiting:
            self._cancel_timer()
            self._waiting = False
            self._armed_shortcut = None
            if definition.command != "start_action" or definition.action_id is None:
                self._on_error("Invalid shortcut sequence.", "Choose an action shortcut after Ctrl+Alt+Q.")
                return None
            return StartAction(definition.action_id, trigger.press_type, "speech")
        return self._shortcuts.resolve(trigger.shortcut_id, trigger.press_type)

    def cancel(self) -> None:
        self._cancel_timer()
        self._armed_shortcut = None
        self._waiting = False

    @property
    def is_waiting(self) -> bool:
        return self._waiting

    def _start_timeout(self) -> None:
        self._cancel_timer()
        self._generation += 1
        generation = self._generation

        def timeout() -> None:
            if generation != self._generation or not self._waiting:
                return
            self._waiting = False
            self._armed_shortcut = None
            self._on_error("Shortcut sequence timed out.", "Hold Ctrl+Alt+Q, then press an action shortcut within one second.")

        self._timer = self._schedule(self._timeout_sec, timeout)

    def _cancel_timer(self) -> None:
        self._generation += 1
        timer, self._timer = self._timer, None
        if timer is not None and hasattr(timer, "cancel"):
            timer.cancel()
