from __future__ import annotations

import threading


class AppOwnedProcessRegistry:
    """Container-owned registry of helper processes that must not become paste targets."""

    def __init__(self) -> None:
        self._process_ids: set[int] = set()
        self._lock = threading.Lock()

    def register(self, process_id: int) -> None:
        if process_id > 0:
            with self._lock:
                self._process_ids.add(process_id)

    def unregister(self, process_id: int) -> None:
        with self._lock:
            self._process_ids.discard(process_id)

    def contains(self, process_id: int) -> bool:
        with self._lock:
            return process_id in self._process_ids
