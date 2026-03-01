from __future__ import annotations


class TrayController:
    def __init__(self, event_bus) -> None:
        self._event_bus = event_bus
        self.last_status = "idle"

    def subscribe(self) -> None:
        self._event_bus.subscribe("ui_status", self._on_status)

    def _on_status(self, payload: dict) -> None:
        self.last_status = str(payload.get("status", "unknown"))
