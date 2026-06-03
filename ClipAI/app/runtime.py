from __future__ import annotations

import logging
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

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
from clipai.services.browser_voice_input import BrowserVoiceInputConfig, BrowserVoiceInputServer
from clipai.services.model_manager import ModelManager
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
        self._model_manager = ModelManager(bundle)
        self._run_state = {"running": False}
        self._listener = None
        self._tray: TrayIcon | None = None
        self._tts_engine: TTSEngine | None = None
        self._tts_service: TTSService | None = None
        self._popup_presenter: PopupPresenter | None = None
        self._popup_sessions: dict[str, PopupSession] = {}
        self._voice_input_process: subprocess.Popen | None = None
        self._browser_voice_input_server: BrowserVoiceInputServer | None = None

    def _active_popup_chain_session(self) -> PopupSession | None:
        if self._popup_presenter is None:
            return None
        session_id = self._popup_presenter.get_active_session_id()
        if not session_id:
            return None
        session = self._popup_sessions.get(session_id)
        if session is None:
            return None
        if not self._popup_presenter.is_session_active(session_id):
            return None
        if not session.is_ready_for_chaining():
            return None
        return session

    @staticmethod
    def _popup_callbacks(popup_session: PopupSession, presenter: PopupPresenter) -> RunCallbacks:
        return RunCallbacks(
            on_input_resolved=lambda resolved: presenter.update_input(
                popup_session.session_id,
                resolved.text,
            ),
            on_chunk=lambda chunk: presenter.append_chunk(
                popup_session.session_id,
                chunk,
            ),
            on_complete=lambda result: presenter.finalize_result(
                popup_session.session_id,
                result.content,
            ),
        )

    def start(self) -> None:
        self._init_tts()
        if self._popup_presenter is not None:
            self._popup_presenter.dispose()
        self._popup_presenter = PopupPresenter(
            on_follow_up=self._submit_follow_up,
            on_session_closed=self._close_popup_session,
            tts_service=self._tts_service,
            event_bus=self._bus,
        )
        self._run_state["running"] = True
        self._register_hotkeys()
        self._init_tray()
        logger.info("[clipai] Desktop runtime started.")
        if self._listener is None:
            logger.info("[clipai] Running without hotkeys.")

    def run_forever(self) -> None:
        try:
            if self._tray is not None:
                self._tray.run(detached=False)
                return
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
        if self._popup_presenter is not None:
            self._popup_presenter.dispose()
            self._popup_presenter = None
        if self._browser_voice_input_server is not None:
            self._browser_voice_input_server.stop()
            self._browser_voice_input_server = None
        logger.info("[clipai] Stopped.")

    def _close_popup_session(self, session_id: str) -> None:
        self._popup_sessions.pop(session_id, None)

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

    def _init_tray(self) -> None:
        self._tray = TrayIcon(
            on_quit_callback=self.stop,
            client=self._model_manager,
            tts_engine=self._tts_engine,
            app_cfg=self._bundle.app_cfg,
            actions_list=self._bundle.actions,
        )

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

        if action_id == "voice_input":
            self._show_voice_input(correlation_id)
            return

        def _worker() -> None:
            popup_session: PopupSession | None = None
            with logging_context(action_id=action_id, correlation_id=correlation_id):
                try:
                    presenter = self._popup_presenter
                    if presenter is None:
                        raise RuntimeError("Popup presenter is not initialized.")
                    self._bus.emit(Events.UI_STATUS, status="processing")
                    popup_session = self._active_popup_chain_session()
                    callbacks = None
                    output_mode_override = None
                    explicit_text = None
                    popup_chain_session_id = None
                    if popup_session is not None:
                        explicit_text = popup_session.latest_result
                        output_mode_override = "popup"
                        popup_chain_session_id = popup_session.session_id
                        popup_session.begin_chained_action(
                            action_id=action_id,
                            action_name=resolved_action.action_name,
                            original_input=explicit_text,
                            action_press_type=resolved_action.press_type,
                            variant_applied=resolved_action.variant_applied,
                            resolved_action_def=action_def,
                        )
                        presenter.refresh_session(popup_session.session_id)
                        callbacks = self._popup_callbacks(popup_session, presenter)
                    elif str(action_def.get("output_mode") or "stdout") == "popup":
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
                        presenter.show_session(popup_session)
                        callbacks = self._popup_callbacks(popup_session, presenter)
                    outcome = self._runner.run_resolved_action(
                        resolved_action,
                        build_runtime_context(
                            mode="desktop_hotkey",
                            apply_output=True,
                            use_selection=popup_session is None,
                            stream_enabled=self._runner._default_stream_enabled(action_def),
                            stream_to_stdout=False,
                            popup_chain_session_id=popup_chain_session_id,
                        ),
                        callbacks=callbacks,
                        explicit_text=explicit_text,
                        output_mode_override=output_mode_override,
                    )
                    logger.info(
                        "[clipai] Execute action completed: action_id=%s output_mode=%s result_chars=%s",
                        action_id,
                        outcome.output_mode,
                        len(outcome.result.content or ""),
                    )

                    if popup_session is not None:
                        popup_session.update_action_metadata(
                            action_id=outcome.action_id,
                            action_name=outcome.action_name,
                            action_press_type=outcome.press_type,
                            variant_applied=resolved_action.variant_applied,
                            resolved_action_def=action_def,
                        )
                        popup_session.update_result_metadata(
                            provider=outcome.provider_name,
                            model=outcome.model_name,
                        )
                        popup_session.mark_input_ready(outcome.input_resolution.text)
                        popup_session.mark_result_ready(outcome.result.content)
                        presenter.refresh_session(popup_session.session_id)
                        presenter.flash_status(popup_session.session_id, "success")

                    self._bus.emit(Events.UI_STATUS, status="success")
                except ValueError as exc:
                    logger.error("[clipai] Execute action validation failed: action_id=%s error=%s", action_id, exc)
                    notify("ClipAI", str(exc))
                    if popup_session is not None:
                        presenter.finalize_result(popup_session.session_id, str(exc))
                        presenter.flash_status(popup_session.session_id, "error")
                    self._bus.emit(Events.UI_STATUS, status="warning")
                except OutputModeError as exc:
                    logger.error("[clipai] %s", exc)
                    notify("ClipAI", str(exc))
                    if popup_session is not None:
                        presenter.finalize_result(popup_session.session_id, str(exc))
                        presenter.flash_status(popup_session.session_id, "error")
                    self._bus.emit(Events.UI_STATUS, status="error")
                except Exception as exc:
                    logger.exception("[clipai] Action failed: %s", exc)
                    notify("ClipAI", f"Action failed: {exc}")
                    if popup_session is not None:
                        presenter.finalize_result(popup_session.session_id, f"Action failed: {exc}")
                        presenter.flash_status(popup_session.session_id, "error")
                    self._bus.emit(Events.UI_STATUS, status="error")

        threading.Thread(target=_worker, daemon=True).start()

    def _show_voice_input(self, correlation_id: str) -> None:
        with logging_context(action_id="voice_input", correlation_id=correlation_id):
            voice_cfg = dict(self._bundle.cfg.get("voice_input", {}) or {})
            backend = str(voice_cfg.get("backend") or voice_cfg.get("mode") or "browser_speech").lower()
            if backend in {"browser_speech", "google", "chrome", "edge"}:
                self._show_browser_voice_input(voice_cfg)
                return

            self._show_webview_voice_input()

    def _show_browser_voice_input(self, voice_cfg: dict[str, object]) -> None:
        try:
            if self._browser_voice_input_server is None or not self._browser_voice_input_server.is_running:
                server_cfg = BrowserVoiceInputConfig.from_mapping(voice_cfg)
                self._browser_voice_input_server = BrowserVoiceInputServer(server_cfg)
            url = self._browser_voice_input_server.start()
            self._open_voice_input_browser(url, voice_cfg)
            logger.info("[clipai] Browser voice input launched: %s", url)
            self._bus.emit(Events.UI_STATUS, status="success")
        except Exception as exc:
            logger.exception("[clipai] Browser voice input launch failed: %s", exc)
            notify("ClipAI", f"Voice input failed: {exc}")
            self._bus.emit(Events.UI_STATUS, status="error")

    def _open_voice_input_browser(self, url: str, voice_cfg: dict[str, object]) -> None:
        browser = str(voice_cfg.get("browser") or "edge").strip().lower()
        browser_path = str(voice_cfg.get("browser_path") or "").strip()
        if browser_path:
            subprocess.Popen([browser_path, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        candidates: list[str] = []
        if browser in {"edge", "msedge"}:
            candidates = [
                "msedge",
                "msedge.exe",
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            ]
        elif browser in {"chrome", "google_chrome", "google-chrome"}:
            candidates = [
                "chrome",
                "chrome.exe",
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            ]

        for candidate in candidates:
            resolved = shutil.which(candidate) or (candidate if os.path.isfile(candidate) else "")
            if resolved:
                subprocess.Popen([resolved, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

        webbrowser.open(url)

    def _show_webview_voice_input(self) -> None:
        if self._voice_input_process is not None and self._voice_input_process.poll() is None:
            notify("ClipAI", "Voice input is already open.")
            return
        if importlib.util.find_spec("webview") is None:
            notify("ClipAI", "Voice input requires pywebview. Install dependencies from requirements.txt.")
            self._bus.emit(Events.UI_STATUS, status="warning")
            return

        try:
            self._voice_input_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "clipai.ui.voice_input_webview",
                    "--config",
                    self._bundle.config_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            logger.info("[clipai] Voice input WebView launched.")
            self._bus.emit(Events.UI_STATUS, status="success")
        except Exception as exc:
            logger.exception("[clipai] Voice input launch failed: %s", exc)
            notify("ClipAI", f"Voice input failed: {exc}")
            self._bus.emit(Events.UI_STATUS, status="error")

    def _read_selection_aloud(self) -> None:
        if self._tts_service is None:
            notify("ClipAI", "TTS is not enabled.")
            return

        resolver = InputResolver(enable_selection_capture=True)
        resolved = resolver.resolve_text(None, input_mode="selection_or_clipboard")
        if resolved.error or not resolved.text.strip():
            notify("ClipAI", resolved.error or "No text selected.")
            return

        logger.info("[clipai] TTS read selection dispatch: chars=%s", len(resolved.text.strip()))
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
        presenter = self._popup_presenter
        if presenter is None:
            notify("ClipAI", "Popup presenter is not initialized.")
            return
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
                presenter.refresh_session(session.session_id)
                callbacks = RunCallbacks(
                    on_chunk=lambda chunk: presenter.append_chunk(session.session_id, chunk),
                    on_complete=lambda result: presenter.finalize_result(session.session_id, result.content),
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
                session.update_result_metadata(
                    provider=outcome.provider_name,
                    model=outcome.model_name,
                )
                session.mark_result_ready(outcome.result.content)
                presenter.refresh_session(session.session_id)
                presenter.flash_status(session.session_id, "success")
            except ValueError as exc:
                presenter.finalize_result(session.session_id, str(exc))
                presenter.flash_status(session.session_id, "error")
            except Exception as exc:
                logger.exception("[clipai] Follow-up failed: %s", exc)
                presenter.finalize_result(session.session_id, f"Follow-up failed: {exc}")
                presenter.flash_status(session.session_id, "error")
            finally:
                presenter.set_follow_up_enabled(session.session_id, True)

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
