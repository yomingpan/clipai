from __future__ import annotations

from ClipAI.actions import load_actions
from ClipAI.app_controller import AppController
from ClipAI.clipboard import read_image_base64, read_text, write_text
from ClipAI.core.event_bus import EventBus
from ClipAI.providers.factory import build_provider
from ClipAI.services.action_service import ActionService
from ClipAI.services.input_receiver import InputReceiver
from ClipAI.services.output_router import OutputRouter
from ClipAI.services.pipeline_coordinator import PipelineCoordinator
from ClipAI.services.rhythm_guard import RhythmGuard
from ClipAI.services.rhythm_mode_manager import RhythmModeManager
from ClipAI.services.rhythm_tracker import RhythmTracker
from ClipAI.services.tts_service import TTSService
from ClipAI.ui.dialog_lifecycle import DialogLifecycle
from ClipAI.ui.result_popup.conversation_state import ConversationState
from ClipAI.ui.result_popup.pipeline_integration import PipelineIntegration
from ClipAI.ui.result_popup.popup import ResultPopup


def build_app(config: dict):
    event_bus = EventBus()
    provider = build_provider(config)

    input_receiver = InputReceiver(read_text, read_image_base64)
    output_router = OutputRouter(
        show_popup=lambda text: None,
        copy_clipboard=write_text,
        auto_paste=lambda text: None,
        notify=lambda text: None,
    )
    pipeline = PipelineCoordinator(event_bus)
    rhythm_mode_manager = RhythmModeManager(event_bus)
    rhythm_tracker = RhythmTracker(event_bus)
    rhythm_guard = RhythmGuard(event_bus)
    tts_service = TTSService(event_bus, speak_fn=lambda text: None)
    action_service = ActionService(event_bus, provider)
    controller = AppController(
        action_service=action_service,
        input_receiver=input_receiver,
        output_router=output_router,
        pipeline_coordinator=pipeline,
        rhythm_mode_manager=rhythm_mode_manager,
        actions_registry=load_actions(),
    )

    event_bus.subscribe(
        "follow_up_request",
        lambda payload: controller.follow_up(payload.get("text", ""), payload.get("action_id", "")),
    )

    ui_bundle: dict = {"dialog_lifecycle": None, "popup": None, "pipeline_integration": None}
    if config.get("enable_ui", False):
        lifecycle = DialogLifecycle(event_bus)
        root = lifecycle.create_root()
        popup = ResultPopup(root)
        state = ConversationState()
        integration = PipelineIntegration(event_bus, popup, state)
        integration.start()
        ui_bundle = {
            "dialog_lifecycle": lifecycle,
            "popup": popup,
            "pipeline_integration": integration,
        }

    return {
        "event_bus": event_bus,
        "provider": provider,
        "input_receiver": input_receiver,
        "output_router": output_router,
        "pipeline": pipeline,
        "rhythm_mode_manager": rhythm_mode_manager,
        "rhythm_tracker": rhythm_tracker,
        "rhythm_guard": rhythm_guard,
        "tts_service": tts_service,
        "action_service": action_service,
        "controller": controller,
        **ui_bundle,
    }
