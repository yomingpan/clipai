from __future__ import annotations

from typing import Callable

from clipai.core.event_bus import EventBus


class DialogLifecycle:
    def __init__(self, event_bus: EventBus, root=None) -> None:
        self._event_bus = event_bus
        self._root = root
        self._subscriptions: list[str] = []
        self._scheduled: list[str] = []

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

    def run_dialog(self, track_dialog_state: bool = True) -> None:
        del track_dialog_state
        self.run()

    def call_on_ui_thread(self, cb: Callable[[], None]) -> None:
        if self._root is None:
            raise RuntimeError("root not created")
        self._root.after(0, cb)

    def close(self) -> None:
        if self._root is None:
            return
        for job in list(self._scheduled):
            try:
                self._root.after_cancel(job)
            except Exception:
                pass
        self._scheduled.clear()
        for sid in list(self._subscriptions):
            try:
                self._event_bus.unsubscribe(sid)
            except Exception:
                pass
        self._subscriptions.clear()
        try:
            self._root.quit()
        except Exception:
            pass
        try:
            self._root.destroy()
        except Exception:
            pass

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> str:
        if self._root is None:
            raise RuntimeError("root not created")
        job = self._root.after(delay_ms, callback)
        self._scheduled.append(job)
        return job

    def add_event_subscription(self, event_name: str, subscription_id: str) -> None:
        del event_name
        self._subscriptions.append(subscription_id)

    def setup_close_on_escape(self, callback: Callable | None = None) -> None:
        if self._root is None:
            raise RuntimeError("root not created")

        def _handler(event=None):
            del event
            if callback:
                callback()
            else:
                self.close()

        self._root.bind("<Escape>", _handler)

    def setup_close_on_focus_out(self, delay_ms: int = 100, callback: Callable | None = None) -> None:
        if self._root is None:
            raise RuntimeError("root not created")

        def _handler(event=None):
            del event
            def _close():
                if callback:
                    callback()
                else:
                    self.close()
            self.schedule(delay_ms, _close)

        self._root.bind("<FocusOut>", _handler)

    def setup_force_focus(self, target_widget=None, delay_ms: int = 100) -> None:
        if self._root is None:
            raise RuntimeError("root not created")

        def _focus():
            try:
                self._root.lift()
                self._root.attributes("-topmost", True)
                self._root.after(250, lambda: self._root.attributes("-topmost", False))
                if target_widget is not None:
                    target_widget.focus_set()
                else:
                    self._root.focus_force()
            except Exception:
                pass

        self.schedule(delay_ms, _focus)
