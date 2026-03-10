from __future__ import annotations

import logging
import multiprocessing
import threading
import time

from clipai.core.event_bus import Events, get_event_bus
from clipai.hotkey import register_hotkeys_with_long_press
from clipai.notification import notify
from clipai.services.action_registry import load_app_config
from clipai.services.action_runner import ActionRunner, RunRequest
from clipai.services.output_applier import OutputModeError
from clipai.services.runtime_context import build_runtime_context
from clipai.tray import TrayIcon

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

logger = logging.getLogger("clipai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    logger.info("[clipai] Starting desktop runtime...")

    if load_dotenv:
        load_dotenv()

    bundle = load_app_config("config/config.yaml")
    bus = get_event_bus()
    runner = ActionRunner(bundle, event_bus=bus)

    run_state = {"running": True}

    def _execute_action(action_id: str) -> None:
        action_def = bundle.action_map.get(action_id)
        if not action_def:
            logger.error("[clipai] Unknown action id: %s", action_id)
            return

        def _worker() -> None:
            try:
                bus.emit(Events.UI_STATUS, status="processing")
                outcome = runner.run(
                    RunRequest(action_id=action_id),
                    build_runtime_context(
                        mode="desktop_hotkey",
                        apply_output=True,
                        use_selection=True,
                        stream_enabled=bool(action_def.get("stream", True)),
                        stream_to_stdout=False,
                    ),
                )

                if outcome.output_mode == "popup":
                    notify("ClipAI", outcome.result.content[:200])

                bus.emit(Events.UI_STATUS, status="success")
            except ValueError as exc:
                notify("ClipAI", str(exc))
                bus.emit(Events.UI_STATUS, status="warning")
            except OutputModeError as exc:
                logger.error("[clipai] %s", exc)
                notify("ClipAI", str(exc))
                bus.emit(Events.UI_STATUS, status="error")
            except Exception as exc:
                logger.exception("[clipai] Action failed: %s", exc)
                notify("ClipAI", f"Action failed: {exc}")
                bus.emit(Events.UI_STATUS, status="error")

        threading.Thread(target=_worker, daemon=True).start()

    listener = None
    try:
        listener = register_hotkeys_with_long_press(bundle.action_map, _execute_action, None)
    except Exception as exc:
        logger.error("[clipai] Hotkey registration unavailable: %s", exc)
        notify("ClipAI", f"Hotkeys unavailable: {exc}")

    tray = TrayIcon(
        on_quit_callback=lambda: run_state.__setitem__("running", False),
        client=None,
        tts_engine=None,
        app_cfg=bundle.app_cfg,
        actions_list=bundle.actions,
        rhythm_mode_manager=None,
        rhythm_reporter=None,
    )
    tray.run()

    logger.info("[clipai] Desktop runtime started.")
    if listener is None:
        logger.info("[clipai] Running without hotkeys.")

    try:
        while run_state["running"]:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("[clipai] Keyboard interrupt received.")
    finally:
        run_state["running"] = False
        if listener is not None:
            listener.stop()
        tray.stop()
        logger.info("[clipai] Stopped.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
