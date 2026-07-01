from __future__ import annotations

import queue
from dataclasses import dataclass

from ClipAI.app.config import ConfigBundle
from ClipAI.platform.clipboard import SystemClipboard
from ClipAI.platform.hotkey import PressType, register_hotkeys_with_long_press
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.vertical_slice import VerticalSliceWorkflow
from ClipAI.ui.result_dialog import ResultDialogPresenter


@dataclass(frozen=True)
class HotkeyEvent:
    action_id: str
    press_type: PressType


class Phase3Runtime:
    def __init__(self, bundle: ConfigBundle) -> None:
        self._bundle = bundle
        self._events: queue.Queue[HotkeyEvent] = queue.Queue()
        self._listener = None
        self._workflow = VerticalSliceWorkflow(
            app_config=bundle.app,
            actions=bundle.actions,
            clipboard=SystemClipboard(),
            provider=FakeProvider(),
            presenter_factory=ResultDialogPresenter,
        )

    def start(self) -> None:
        self._listener = register_hotkeys_with_long_press(
            self._bundle.actions.hotkey_action_map(),
            self._enqueue_hotkey,
            modifier_mode=self._bundle.app.modifier_mode,
        )

    def run_forever(self) -> None:
        print("[clipai] Phase 3 runtime ready. Press Ctrl+C to stop.")
        try:
            while True:
                event = self._events.get()
                self._workflow.run(event.action_id, event.press_type)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _enqueue_hotkey(self, action_id: str, press_type: PressType) -> None:
        self._events.put(HotkeyEvent(action_id=action_id, press_type=press_type))
