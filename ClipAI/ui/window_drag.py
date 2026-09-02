from __future__ import annotations

from typing import Protocol


class _DraggableWindow(Protocol):
    def winfo_x(self) -> int: ...

    def winfo_y(self) -> int: ...

    def geometry(self, value: str) -> object: ...


class _DragHandle(Protocol):
    def bind(self, event_name: str, callback, add: str | None = None) -> object: ...


class WindowDragController:
    """Own pointer offsets and geometry updates for one toolkit window."""

    def __init__(self, window: _DraggableWindow) -> None:
        self._window = window
        self._offset_x = 0
        self._offset_y = 0

    def bind(self, *handles: _DragHandle) -> None:
        for handle in handles:
            handle.bind("<ButtonPress-1>", self._start, add="+")
            handle.bind("<B1-Motion>", self._move, add="+")

    def _start(self, event) -> None:
        self._offset_x = int(event.x_root) - int(self._window.winfo_x())
        self._offset_y = int(event.y_root) - int(self._window.winfo_y())

    def _move(self, event) -> None:
        x = int(event.x_root) - self._offset_x
        y = int(event.y_root) - self._offset_y
        self._window.geometry(f"+{x}+{y}")
