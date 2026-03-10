import logging
import multiprocessing
from typing import Any, Dict, Optional

from clipai.hotkeys import register_hotkeys_with_long_press
from clipai.tray import TrayIcon
from clipai.app_factory import AppFactory
from clipai.core import memory_manager
from clipai.ui.base_dialog import init_shared_root, get_shared_root

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

logger = logging.getLogger("clipai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _load_config_safe(path: str) -> Dict[str, Any]:
    """
    Your original code referenced load_config("config/config.yaml") but did not import it.
    Try to import from common locations; adjust as needed for your project structure.
    """
    # ✅ 你可以把下面其中一個 import 改成你實際的路徑
    try:
        from clipai.config import load_config  # type: ignore
        return load_config(path)
    except Exception:
        pass

    try:
        from clipai.services.resolve_config import load_config  # type: ignore
        return load_config(path)
    except Exception:
        pass

    raise ImportError(
        "load_config() not found. Please import it from your project, "
        "e.g. `from clipai.config import load_config`."
    )


def main() -> None:
    logger.info("[clipai] Starting...")

    if load_dotenv:
        load_dotenv()

    cfg = _load_config_safe("config/config.yaml")
    app_cfg = cfg.get("app", {}) or {}

    if app_cfg.get("debug", False):
        logger.setLevel(logging.DEBUG)
        memory_manager.set_debug_mode(True)
        logger.debug("[clipai] Debug mode enabled")

    # AppFactory.create(cfg) -> services dict
    services: Dict[str, Any] = AppFactory.create(cfg)

    provider = services.get("provider")
    tts_engine = services.get("tts_engine")
    actions_list = services.get("action_list")
    controller = services.get("controller")
    rhythm_mode_manager = services.get("rhythm_mode_manager")

    event_logger = services.get("event_logger")
    rhythm_tracker = services.get("rhythm_tracker")
    rhythm_guard = services.get("rhythm_guard")
    rhythm_reporter = services.get("rhythm_reporter")

    # start background services if they exist
    for svc, name in [
        (event_logger, "event_logger"),
        (rhythm_tracker, "rhythm_tracker"),
        (rhythm_guard, "rhythm_guard"),
        (rhythm_reporter, "rhythm_reporter"),
    ]:
        if svc and hasattr(svc, "start"):
            logger.debug("[clipai] starting %s ...", name)
            svc.start()

    tts_service = services.get("tts_service") or services.get("tts_services")  # tolerate naming
    action_map = services.get("action_map")

    listener = None
    running = True
    tray: Optional[TrayIcon] = None

    def stop_app() -> None:
        nonlocal running, listener, tray
        running = False
        logger.info("[clipai] Stopping...")

        try:
            if listener:
                listener.stop()
        except Exception:
            logger.exception("[clipai] Failed to stop hotkey listener")

        try:
            if tray:
                tray.stop()
        except Exception:
            logger.exception("[clipai] Failed to stop tray")

    # Register hotkeys (long press)
    if controller and action_map:
        def _is_speaking() -> bool:
            if tts_service and hasattr(tts_service, "is_speaking"):
                try:
                    return bool(tts_service.is_speaking())
                except Exception:
                    return False
            return False

        listener = register_hotkeys_with_long_press(
            action_map,
            controller.dispatch,
            controller.dispatch_long_press,
            tts_check_fn=_is_speaking,
        )

    # Tray icon
    tray = TrayIcon(
        on_quit_callback=stop_app,
        client=provider,
        tts_engine=tts_engine,
        app_cfg=app_cfg,
        actions_list=actions_list,
        rhythm_mode_manager=rhythm_mode_manager,
        rhythm_reporter=rhythm_reporter,
    )

    if controller and hasattr(controller, "set_tray"):
        controller.set_tray(tray)

    tray.run()

    logger.info("[clipai] Running... (System Tray icon active)")
    logger.info("[clipai] Press Ctrl+C or use Tray Icon to stop.")

    # Tk root shared
    init_shared_root()
    shared_root = get_shared_root()
    assert shared_root is not None, "shared Tk root failed to initialize"

    def _check_alive() -> None:
        # listener might not exist depending on config
        listener_ok = True
        if listener is not None:
            listener_ok = getattr(listener, "running", True)

        if (not running) or (not listener_ok):
            try:
                shared_root.quit()
            except Exception:
                pass
            return

        shared_root.after(500, _check_alive)

    shared_root.after(500, _check_alive)

    try:
        shared_root.mainloop()
    except KeyboardInterrupt:
        stop_app()
    finally:
        stop_app()
        logger.info("[clipai] Stopped.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()