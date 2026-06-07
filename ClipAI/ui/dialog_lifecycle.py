from __future__ import annotations

import tkinter as tk
from typing import Callable


class DialogLifecycle:
    def __init__(self, event_bus, root: tk.Misc) -> None:
        self._event_bus = event_bus
        self._root = root
        self._scheduled_jobs: list[str] = []
        self._unsubscribers: list[Callable[[], None]] = []
        self._closed = False

    def run_dialog(self) -> None:
        if not self._closed:
            self._root.mainloop()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for job_id in list(self._scheduled_jobs):
            try:
                self._root.after_cancel(job_id)
            except tk.TclError:
                pass
        self._scheduled_jobs.clear()

        for unsubscribe in list(self._unsubscribers):
            unsubscribe()
        self._unsubscribers.clear()

        try:
            self._root.quit()
        except tk.TclError:
            pass
        try:
            self._root.destroy()
        except tk.TclError:
            pass

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> str:
        def run_once() -> None:
            if job_id in self._scheduled_jobs:
                self._scheduled_jobs.remove(job_id)
            if not self._closed:
                callback()

        job_id = self._root.after(delay_ms, run_once)
        self._scheduled_jobs.append(job_id)
        return job_id

    def cancel(self, job_id: str) -> None:
        if job_id in self._scheduled_jobs:
            self._scheduled_jobs.remove(job_id)
        try:
            self._root.after_cancel(job_id)
        except tk.TclError:
            pass

    def subscribe(self, event_name: str, callback: Callable[[object], None]) -> None:
        self._unsubscribers.append(self._event_bus.subscribe(event_name, callback))

    def focus(self, widget: tk.Misc | None = None) -> None:
        target = widget or self._root
        try:
            target.focus_force()
        except tk.TclError:
            pass
