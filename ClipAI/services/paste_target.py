from __future__ import annotations

import threading

from ClipAI.core.models import PasteTarget
from ClipAI.core.ports import PasteTargetPresenter


class PasteTargetCoordinator:
    """Own the latest observed non-ClipAI foreground window."""

    def __init__(self, presenter: PasteTargetPresenter | None = None) -> None:
        self._presenter = presenter
        self._target: PasteTarget | None = None
        self._lock = threading.RLock()

    @property
    def current(self) -> PasteTarget | None:
        with self._lock:
            return self._target

    def observe(self, target: PasteTarget) -> bool:
        with self._lock:
            if self._target is not None and target.observation_sequence <= self._target.observation_sequence:
                return False
            self._target = target
        if self._presenter is not None:
            self._presenter.present_paste_target(target)
        return True
