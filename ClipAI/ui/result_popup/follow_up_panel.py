from __future__ import annotations

import tkinter as tk

from ClipAI.core.constants import EVENT_FOLLOW_UP_REQUEST


class FollowUpPanel:
    def __init__(self, root, event_bus, action_id_getter) -> None:
        self._event_bus = event_bus
        self._action_id_getter = action_id_getter
        self.frame = tk.Frame(root)
        self.entry = tk.Entry(self.frame, width=60)
        self.entry.pack(side="left", fill="x", expand=True)
        tk.Button(self.frame, text="Send", command=self._emit).pack(side="left")

    def _emit(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self._event_bus.publish(
            EVENT_FOLLOW_UP_REQUEST,
            {"text": text, "action_id": self._action_id_getter() or ""},
        )
        self.entry.delete(0, "end")
