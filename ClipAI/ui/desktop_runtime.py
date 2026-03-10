from __future__ import annotations

import logging
import threading
import time

from clipai.core.event_bus import Events, get_event_bus
from clipai.hotkey import register_hotkeys_with_long_press
from clipai.notification import notify
from clipai.services.action_registry import AppConfigBundle
from clipai.services.action_runner import ActionRunner, RunCallbacks, RunRequest
from clipai.services.output_applier import OutputModeError
from clipai.services.runtime_context import build_runtime_context
from clipai.ui.popup_presenter import PopupPresenter
from clipai.ui.result_popup.popup_session import PopupSession
from clipai.tray import TrayIcon

logger = logging.getLogger("clipai")


class DesktopRuntime:
    def __init__(self, bundle: AppConfigBundle) -> None:
        self._bundle = bundle
        self._bus = get_event_bus()
        self._runner = ActionRunner(bundle, event_bus=self._bus)
        self._run_state = {"running": False}
        self._listener = None
        self._tray: TrayIcon | None = None
        self._popup_presenter = PopupPresenter()

    def start(self) -> None:
        self._run_state["running"] = True
        self._register_hotkeys()
        self._start_tray()
        logger.info("[clipai] Desktop runtime started.")
        if self._listener is None:
            logger.info("[clipai] Running without hotkeys.")

    def run_forever(self) -> None:
        try:
            while self._run_state["running"]:
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("[clipai] Keyboard interrupt received.")
        finally:
            self.stop()

    def stop(self) -> None:
        if not self._run_state["running"]:
            return
        self._run_state["running"] = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        logger.info("[clipai] Stopped.")

    def _register_hotkeys(self) -> None:
        try:
            self._listener = register_hotkeys_with_long_press(self._bundle.action_map, self._execute_action, None)
        except Exception as exc:
            logger.error("[clipai] Hotkey registration unavailable: %s", exc)
            notify("ClipAI", f"Hotkeys unavailable: {exc}")

    def _start_tray(self) -> None:
        self._tray = TrayIcon(
            on_quit_callback=self.stop,
            client=None,
            tts_engine=None,
            app_cfg=self._bundle.app_cfg,
            actions_list=self._bundle.actions,
            rhythm_mode_manager=None,
            rhythm_reporter=None,
        )
        self._tray.run()

    def _execute_action(self, action_id: str) -> None:
        action_def = self._bundle.action_map.get(action_id)
        if not action_def:
            logger.error("[clipai] Unknown action id: %s", action_id)
            return

        def _worker() -> None:
            try:
                self._bus.emit(Events.UI_STATUS, status="processing")
                popup_session = None
                callbacks = None
                if str(action_def.get("output_mode") or "stdout") == "popup":
                    popup_session = PopupSession(
                        action_id=action_id,
                        action_name=str(action_def.get("name") or action_id),
                        original_input="Connecting...",
                        latest_result="Connecting...",
                    )
                    self._popup_presenter.show_session(popup_session)
                    callbacks = RunCallbacks(
                        on_input_resolved=lambda resolved: self._popup_presenter.update_input(
                            popup_session.session_id,
                            resolved.text,
                        ),
                        on_chunk=lambda chunk: self._popup_presenter.append_chunk(
                            popup_session.session_id,
                            chunk,
                        ),
                        on_complete=lambda result: self._popup_presenter.finalize_result(
                            popup_session.session_id,
                            result.content,
                        ),
                    )
                outcome = self._runner.run(
                    RunRequest(action_id=action_id),
                    build_runtime_context(
                        mode="desktop_hotkey",
                        apply_output=True,
                        use_selection=True,
                        stream_enabled=bool(action_def.get("stream", True)),
                        stream_to_stdout=False,
                    ),
                    callbacks=callbacks,
                )

                if popup_session is not None:
                    popup_session.action_id = outcome.action_id
                    popup_session.action_name = outcome.action_name
                    popup_session.original_input = outcome.input_resolution.text
                    popup_session.latest_result = outcome.result.content
                    self._popup_presenter.flash_status(popup_session.session_id, "success")

                self._bus.emit(Events.UI_STATUS, status="success")
            except ValueError as exc:
                notify("ClipAI", str(exc))
                if popup_session is not None:
                    self._popup_presenter.finalize_result(popup_session.session_id, str(exc))
                    self._popup_presenter.flash_status(popup_session.session_id, "error")
                self._bus.emit(Events.UI_STATUS, status="warning")
            except OutputModeError as exc:
                logger.error("[clipai] %s", exc)
                notify("ClipAI", str(exc))
                if popup_session is not None:
                    self._popup_presenter.finalize_result(popup_session.session_id, str(exc))
                    self._popup_presenter.flash_status(popup_session.session_id, "error")
                self._bus.emit(Events.UI_STATUS, status="error")
            except Exception as exc:
                logger.exception("[clipai] Action failed: %s", exc)
                notify("ClipAI", f"Action failed: {exc}")
                if popup_session is not None:
                    self._popup_presenter.finalize_result(popup_session.session_id, f"Action failed: {exc}")
                    self._popup_presenter.flash_status(popup_session.session_id, "error")
                self._bus.emit(Events.UI_STATUS, status="error")

        threading.Thread(target=_worker, daemon=True).start()
