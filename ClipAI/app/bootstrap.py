"""Application factory for assembling ClipAI services."""
from typing import Any, Dict

from clipai.actions import load_actions, build_action_map
from clipai.providers.factory import create_provider
from clipai.platform.tray import markdown_enabled
from clipai.platform.tts import TTSEngine
from clipai.services.action_service import ActionService
from clipai.services.action_handlers import create_default_registry
from clipai.services.event_logger import EventLogger
from clipai.services.input_resolver import InputResolver
from clipai.services.output_router import OutputRouter
from clipai.services.tts_service import TTSService
from clipai.app_controller import AppController


class AppFactory:
    """Builds the entire ClipAI service graph from configuration."""

    @staticmethod
    def create(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Build the entire service graph from config.

        Returns a dict containing core objects needed by main:
        provider, tts_engine, tts_service, action_map, actions_list, controller,
        and event_logger.
        """
        provider_cfg = cfg.get("provider", {})
        app_cfg = cfg.get("app", {})
        tts_cfg = cfg.get("tts", {})
        provider = create_provider(provider_cfg)

        tts_engine = None
        if tts_cfg.get("enabled", False):
            tts_engine = TTSEngine(
                voice=tts_cfg.get("voice", "zh-TW-HsiaoChenNeural"),
                rate=tts_cfg.get("rate", "+0%"),
                volume=tts_cfg.get("volume", "+0%"),
                proxy=tts_cfg.get("proxy")
            )

        tts_service = TTSService(engine=tts_engine)

        actions_list = load_actions("config/config.yaml")
        action_map = build_action_map(actions_list)

        action_service = ActionService(
            provider=provider,
            app_cfg=app_cfg,
            provider_cfg=provider_cfg,
        )
        input_resolver = InputResolver(app_cfg=app_cfg)
        output_router = OutputRouter(app_cfg=app_cfg, markdown_enabled=markdown_enabled)

        event_logger = EventLogger()

        controller = AppController(
            app_cfg=app_cfg,
            action_map=action_map,
            action_service=action_service,
            input_resolver=input_resolver,
            output_router=output_router,
            tts_service=tts_service,
            action_handler_registry=create_default_registry(),
        )

        return {
            "provider": provider,
            "tts_engine": tts_engine,
            "tts_service": tts_service,
            "actions_list": actions_list,
            "action_map": action_map,
            "controller": controller,
            "event_logger": event_logger,
        }


