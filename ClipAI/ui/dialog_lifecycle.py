from __future__ import annotations

from typing import Callable

from clipai.core.event_bus import EventBus


class DialogLifecycle:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._root = None

    def create_root(self):
        import tkinter as tk

        self._root = tk.Tk()
        self._root.withdraw()
        self._event_bus.bind_ui_dispatcher(lambda cb: self._root.after(0, cb))
        return self._root

    def run(self) -> None:
        if self._root is None:
            self.create_root()
        self._root.mainloop()

    def call_on_ui_thread(self, cb: Callable[[], None]) -> None:
        if self._root is None:
            raise RuntimeError("root not created")
        self._root.after(0, cb)
