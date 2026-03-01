from __future__ import annotations

import time
import uuid

from ClipAI.services.action_handlers import build_messages
from ClipAI.services.resolve_config import resolve_action_config


class AppController:
    def __init__(
        self,
        action_service,
        input_receiver,
        output_router,
        pipeline_coordinator,
        rhythm_mode_manager,
        actions_registry,
    ) -> None:
        self._action_service = action_service
        self._input_receiver = input_receiver
        self._output_router = output_router
        self._pipeline_coordinator = pipeline_coordinator
        self._rhythm_mode_manager = rhythm_mode_manager
        self._actions_registry = actions_registry

    def run_action(self, action_key: str, runtime_flags: dict | None = None) -> str:
        action_def = self._actions_registry[action_key]
        config = resolve_action_config(action_def, mode=self._rhythm_mode_manager.mode, runtime_flags=runtime_flags)

        session_id = str(uuid.uuid4())
        self._pipeline_coordinator.start_session(session_id, config.action_id, cancel_previous=True)
        token = self._pipeline_coordinator.token_for(session_id)

        snapshot = self._input_receiver.collect()
        messages = build_messages(action_key, snapshot.text, config.template)
        result = self._action_service.run_action(
            config=config,
            messages=messages,
            rhythm_params=self._rhythm_mode_manager.params(),
            cancellation_token=token,
            source_meta={"image_base64": snapshot.image_base64},
        )
        self._output_router.route(result.content, config.output)
        return result.action_id

    def follow_up(self, text: str, action_id: str) -> str:
        del action_id
        return self.run_action("summarize", runtime_flags={"action_id": f"follow-up-{int(time.time())}"})

    def cancel_current(self) -> None:
        sid = self._pipeline_coordinator.current_session_id
        if sid:
            self._pipeline_coordinator.cancel_session(sid, reason="manual cancel")

    def set_mode(self, mode: str) -> None:
        self._rhythm_mode_manager.set_mode(mode)
