from __future__ import annotations

import logging
import threading
import time

from clipai.app.config import AppConfigBundle
from clipai.actions import ResolvedAction, resolve_action_variant
from clipai.context.input_resolver import InputResolver
from clipai.context.runtime_context import build_runtime_context
from clipai.core.event_bus import Events, get_event_bus
from clipai.platform.hotkey import register_hotkeys_with_long_press
from clipai.platform.notification import notify
from clipai.platform.tts import TTSEngine
from clipai.platform.tts_service import TTSService
from clipai.logging_setup import logging_context, new_correlation_id
from clipai.services.action_runner import ActionRunner, RunCallbacks
from clipai.services.output_applier import OutputModeError
from clipai.services.popup_session import PopupSession
from clipai.ui.popup_presenter import PopupPresenter
from clipai.platform.tray import TrayIcon

logger = logging.getLogger("clipai")


class DesktopRuntime:
    def __init__(self, bundle: AppConfigBundle) -> None:
        self._bundle = bundle
        self._bus = get_event_bus()
        self._runner = ActionRunner(bundle, event_bus=self._bus)
        self._run_state = {"running": False}
        self._listener = None
        self._tray: TrayIcon | None = None
        self._tts_engine: TTSEngine | None = None
        self._tts_service: TTSService | None = None
        self._popup_presenter = PopupPresenter(on_follow_up=self._submit_follow_up)
        self._popup_sessions: dict[str, PopupSession] = {}

    def start(self) -> None:
        self._init_tts()
        self._popup_presenter = PopupPresenter(on_follow_up=self._submit_follow_up, tts_service=self._tts_service)
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
            self._listener = register_hotkeys_with_long_press(
                self._bundle.action_map,
                self._execute_action,
                modifier_mode=str(self._bundle.app_cfg.get("hotkey_modifier_mode") or "ctrl_alt"),
            )
        except Exception as exc:
            logger.error("[clipai] Hotkey registration unavailable: %s", exc)
            notify("ClipAI", f"Hotkeys unavailable: {exc}")

    def _start_tray(self) -> None:
        self._tray = TrayIcon(
            on_quit_callback=self.stop,
            client=None,
            tts_engine=self._tts_engine,
            app_cfg=self._bundle.app_cfg,
            actions_list=self._bundle.actions,
        )
        self._tray.run()

    def _init_tts(self) -> None:
        tts_cfg = self._bundle.tts_cfg
        if not tts_cfg.get("enabled", False):
            self._tts_engine = None
            self._tts_service = None
            return
        self._tts_engine = TTSEngine(
            voice=tts_cfg.get("voice", "zh-TW-HsiaoChenNeural"),
            rate=tts_cfg.get("rate", "+0%"),
            volume=tts_cfg.get("volume", "+0%"),
            proxy=tts_cfg.get("proxy"),
        )
        self._tts_service = TTSService(
            self._bus,
            self._tts_engine.speak,
            stop_fn=self._tts_engine.stop,
            is_speaking_fn=self._tts_engine.is_speaking,
        )

    def _execute_action(self, action_id: str, press_type: str = "short") -> None:
        base_action_def = self._bundle.action_map.get(action_id)
        if not base_action_def:
            logger.error("[clipai] Unknown action id: %s", action_id)
            return
        resolved_action = resolve_action_variant(base_action_def, press_type)
        action_def = resolved_action.action_def
        correlation_id = new_correlation_id()
        with logging_context(action_id=action_id, correlation_id=correlation_id):
            logger.info(
                "[clipai] Execute action requested: action_id=%s press_type=%s resolved_action_name=%s output_mode=%s stream=%s variant_applied=%s",
                action_id,
                resolved_action.press_type,
                resolved_action.action_name,
                action_def.get("output_mode"),
                action_def.get("stream"),
                resolved_action.variant_applied,
            )

        if action_id == "tts_read_selection":
            def _tts_worker() -> None:
                with logging_context(action_id=action_id, correlation_id=correlation_id):
                    self._read_selection_aloud()

            threading.Thread(target=_tts_worker, daemon=True).start()
            return

        def _worker() -> None:
            with logging_context(action_id=action_id, correlation_id=correlation_id):
                try:
                    self._bus.emit(Events.UI_STATUS, status="processing")
                    popup_session = None
                    callbacks = None
                    if str(action_def.get("output_mode") or "stdout") == "popup":
                        popup_session = PopupSession(
                            action_id=action_id,
                            action_name=resolved_action.action_name,
                            original_input="",
                            latest_result="",
                            action_press_type=resolved_action.press_type,
                            variant_applied=resolved_action.variant_applied,
                            resolved_action_def=dict(action_def),
                            input_loading=True,
                            result_loading=True,
                        )
                        self._popup_sessions[popup_session.session_id] = popup_session
                        logger.debug("[clipai] Popup session created: action_id=%s session_id=%s", action_id, popup_session.session_id)
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
                    outcome = self._runner.run_resolved_action(
                        resolved_action,
                        build_runtime_context(
                            mode="desktop_hotkey",
                            apply_output=True,
                            use_selection=True,
                            stream_enabled=self._runner._default_stream_enabled(action_def),
                            stream_to_stdout=False,
                        ),
                        callbacks=callbacks,
                    )
                    logger.info(
                        "[clipai] Execute action completed: action_id=%s output_mode=%s result_chars=%s",
                        action_id,
                        outcome.output_mode,
                        len(outcome.result.content or ""),
                    )

                    if popup_session is not None:
                        popup_session.action_id = outcome.action_id
                        popup_session.action_name = outcome.action_name
                        popup_session.action_press_type = outcome.press_type
                        popup_session.mark_input_ready(outcome.input_resolution.text)
                        popup_session.mark_result_ready(outcome.result.content)
                        self._popup_presenter.refresh_session(popup_session.session_id)
                        self._popup_presenter.flash_status(popup_session.session_id, "success")

                    self._bus.emit(Events.UI_STATUS, status="success")
                except ValueError as exc:
                    logger.error("[clipai] Execute action validation failed: action_id=%s error=%s", action_id, exc)
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

    def _read_selection_aloud(self) -> None:
        if self._tts_service is None:
            notify("ClipAI", "TTS is not enabled.")
            return

        resolver = InputResolver(enable_selection_capture=True)
        resolved = resolver.resolve_text(None, input_mode="selection_or_clipboard")
        if resolved.error or not resolved.text.strip():
            notify("ClipAI", resolved.error or "No text selected.")
            return

        notify("ClipAI", "Reading selected text...")
        self._tts_service.speak_async(resolved.text)

    def _submit_follow_up(self, session: PopupSession, prompt_text: str) -> None:
        correlation_id = new_correlation_id()
        threading.Thread(
            target=self._run_follow_up,
            args=(session, prompt_text, correlation_id),
            daemon=True,
        ).start()

    def _run_follow_up(self, session: PopupSession, prompt_text: str, correlation_id: str) -> None:
        action_def = dict(session.resolved_action_def)
        if not action_def:
            base_action_def = self._bundle.action_map.get(session.action_id)
            if base_action_def is None:
                notify("ClipAI", f"Unknown action id: {session.action_id}")
                return
            resolved_action = resolve_action_variant(base_action_def, session.action_press_type)
            action_def = dict(resolved_action.action_def)
        else:
            resolved_action = ResolvedAction(
                action_id=session.action_id,
                press_type=session.action_press_type,
                action_def=action_def,
                variant_applied=session.variant_applied,
            )
        if not action_def:
            notify("ClipAI", f"Unknown action id: {session.action_id}")
            return

        model = str(action_def.get("model") or self._bundle.provider_cfg.get("default_model") or "")
        with logging_context(action_id=session.action_id, correlation_id=correlation_id):
            try:
                session.start_round(kind="follow_up", prompt_text=prompt_text, model=model or "default")
                self._popup_presenter.refresh_session(session.session_id)
                callbacks = RunCallbacks(
                    on_chunk=lambda chunk: self._popup_presenter.append_chunk(session.session_id, chunk),
                    on_complete=lambda result: self._popup_presenter.finalize_result(session.session_id, result.content),
                )
                outcome = self._runner.run_resolved_action(
                    resolved_action,
                    build_runtime_context(
                        mode="desktop_hotkey",
                        apply_output=False,
                        use_selection=False,
                        stream_enabled=self._runner._default_stream_enabled(action_def),
                        stream_to_stdout=False,
                    ),
                    callbacks=callbacks,
                    explicit_text=prompt_text,
                    explicit_messages=self._build_follow_up_messages(session, action_def, prompt_text),
                )
                session.latest_result = outcome.result.content
                self._popup_presenter.refresh_session(session.session_id)
                self._popup_presenter.flash_status(session.session_id, "success")
            except ValueError as exc:
                self._popup_presenter.finalize_result(session.session_id, str(exc))
                self._popup_presenter.flash_status(session.session_id, "error")
            except Exception as exc:
                logger.exception("[clipai] Follow-up failed: %s", exc)
                self._popup_presenter.finalize_result(session.session_id, f"Follow-up failed: {exc}")
                self._popup_presenter.flash_status(session.session_id, "error")
            finally:
                self._popup_presenter.set_follow_up_enabled(session.session_id, True)

    def _build_follow_up_messages(
        self,
        session: PopupSession,
        action_def: dict[str, object],
        prompt_text: str,
    ) -> list[dict[str, str]]:
        global_prompt = str(self._bundle.app_cfg.get("system_prompt", "")).strip()
        action_prompt = str(action_def.get("system_prompt", "")).strip()
        system_parts = [part for part in (global_prompt, action_prompt) if part]
        system_parts.append(
            "You are continuing an existing ClipAI popup session. "
            "Use the provided context, answer the user's follow-up directly, and do not lose the original meaning."
        )
        return [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {
                "role": "user",
                "content": (
                    f"{session.as_context_text()}\n\n"
                    f"[User Follow-up]\n{prompt_text}"
                ),
            },
        ]
