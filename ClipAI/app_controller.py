import time
import threading
from time import perf_counter
from typing import Dict, List, Optional
import pynput
from clipai.diag_timing import diag

from clipai.platform.clipboard import read_clipboard_text, write_clipboard_text
from clipai.shared.safety import apply_safety
from clipai.shared.logging_utils import log_event, logger
from clipai.platform.notification import notify
from clipai.platform.tray import markdown_enabled
from clipai.dialog import (
    get_user_input, show_result_popup, get_rewrite_options,
    show_memory_confirmation, show_memory_viewer
)
from clipai import memory_manager
from clipai.core.cancellation import get_cancellation_controller
from clipai.core.event_bus import get_event_bus, Events
from clipai.services.action_handlers import ActionHandlerRegistry, create_default_registry
from clipai.services.pipeline_coordinator import get_pipeline_coordinator
from clipai.services.resolved_config import ResolvedActionConfig
from clipai.utils.tts_transform import (
    TTS_PROMPT_SUFFIX, sanitize_for_tts, should_use_full_transform
)

import logging

class AppController:
    """
    Central controller for ClipAI action dispatch and execution.
    Extracted from main.py to improve testability and reduce God Function.
    """
    
    def __init__(self, app_cfg, action_map, action_service, input_resolver,
                 output_router, tts_service, tray=None,
                 action_handler_registry: Optional[ActionHandlerRegistry] = None):
        self._app_cfg = app_cfg
        self._action_map = action_map
        self._action_service = action_service
        self._input_resolver = input_resolver
        self._output_router = output_router
        self._tts_service = tts_service
        self._tray = tray
        self._bus = get_event_bus()
        self._cancel = get_cancellation_controller()
        self._pipeline = get_pipeline_coordinator()
        if action_handler_registry is None:
            self._handler_registry = create_default_registry()
        else:
            self._handler_registry = action_handler_registry
        
        # Concurrency control
        self._semaphore = threading.Semaphore(1)
        self._last_ignored = {"time": 0.0}
        self._action_debounce: Dict[str, float] = {}
        self._debounce_lock = threading.Lock()
    
    def set_tray(self, tray):
        """Set tray after construction (tray is created after controller)."""
        self._tray = tray

    def dispatch(self, action_id, tts_output=False):
        """Handle a normal hotkey press dispatch."""
        def _handle(action, is_pipeline):
            if tts_output:
                # TTS modifier active: bypass special handlers, use LLM pipeline
                # with TTS output (speak result instead of popup)
                user_input_pipeline = "Pipeline Mode" if is_pipeline else None
                self._cancel.clear_cancel_event()
                self.handle_action(
                    action,
                    user_input_override=user_input_pipeline,
                    tts_output=True,
                )
                return

            # Check for a registered special handler (Strategy Pattern)
            handler = self._handler_registry.get(action)
            if handler:
                handler.handle(action, self, is_pipeline)
            else:
                # Default: LLM pipeline
                user_input_pipeline = "Pipeline Mode" if is_pipeline else None
                self._cancel.clear_cancel_event()
                self.handle_action(
                    action,
                    user_input_override=user_input_pipeline,
                )

        self._dispatch_with_guard(action_id, _handle)

    def dispatch_long_press(self, action_id):
        """Handle a long-press hotkey dispatch."""
        def _handle(action, is_pipeline):
            # Check for a registered special handler with long-press support
            handler = self._handler_registry.get(action)
            if handler:
                handler.handle_long_press(action, self, is_pipeline)
            else:
                # Default: enable show_dialog for any action with supports_long_press
                if action.get("supports_long_press", False):
                    action = {**action, "show_dialog": True}
                self.handle_action(action)

        self._dispatch_with_guard(action_id, _handle, debounce_key=f"lp_{action_id}", debounce_sec=1.0)

    def _dispatch_with_guard(self, action_id, handler_fn, debounce_key=None, debounce_sec=0.8):
        """Common dispatch guard: debounce, cancel bypass, semaphore, pipeline mode."""
        diag.mark("dispatch_guard_enter")
        db_key = debounce_key or action_id

        # Debounce check
        now = time.time()
        with self._debounce_lock:
            last_time = self._action_debounce.get(db_key, 0)
            if now - last_time < debounce_sec:
                diag.mark("debounced_skip")
                return
            self._action_debounce[db_key] = now

        # Cancel bypass: cancellation should not be gated by the semaphore
        if action_id == "cancel_action":
            self._cancel.set_cancel_event()
            self._cancel.interrupt_active_action()
            notify("ClipAI", "正在取消 API 調用...")
            return

        # Pipeline Mode: bypass semaphore when dialog is active
        is_pipeline = self._pipeline.is_dialog_active()
        diag.mark("semaphore_try", is_pipeline=is_pipeline)

        if is_pipeline or self._semaphore.acquire(blocking=False):
            diag.mark("semaphore_acquired")
            try:
                action = self._action_map[action_id]
                handler_fn(action, is_pipeline)
            finally:
                if not is_pipeline:
                    self._semaphore.release()
        else:
            diag.mark("semaphore_blocked")
            now = time.time()
            if now - self._last_ignored["time"] > 1.0:
                self._last_ignored["time"] = now
                print("[clipai] Action ignored: another action is already in progress.")
                notify("ClipAI", "請稍候，上一個任務還在處理中...")

    def handle_action(self, action, user_input_override=None, tts_output=False):
        """Execute an action (formerly the top-level handle_action function)."""
        diag.mark("handle_action_enter")
        action_name = action.get('name', 'Unknown')
        output_cfg = action.get("output", {})
        
        self._bus.emit(Events.UI_STATUS, status="processing")

        # Auto-copy if explicitly enabled in output config
        if output_cfg.get("auto_copy_before", False):
            if self._pipeline.is_dialog_active():
                print(f"[clipai] Pipeline Mode: Skipping auto-copy for {action_name} because dialog is active")
            else:
                print(f"[clipai] Triggering auto-copy (Ctrl+C) for {action_name}")
                diag.mark("auto_copy_start")
                # Snapshot clipboard before Ctrl+C for change detection
                try:
                    old_clipboard = read_clipboard_text(retries=1, delay=0)
                except Exception:
                    old_clipboard = None
                time.sleep(0.15)  # wait for focus switch (reduced from 0.3)
                keyboard = pynput.keyboard.Controller()
                keyboard.press(pynput.keyboard.Key.ctrl)
                keyboard.press('c')
                keyboard.release('c')
                keyboard.release(pynput.keyboard.Key.ctrl)
                # Poll for clipboard change instead of hardcoded sleep(0.5)
                # Max 300ms (30 iterations × 10ms), but breaks early on change
                for _ in range(30):
                    time.sleep(0.01)
                    try:
                        new_clipboard = read_clipboard_text(retries=1, delay=0)
                        if new_clipboard != old_clipboard:
                            break
                    except Exception:
                        pass
                diag.mark("auto_copy_done")

        notify("ClipAI", f"正在處理: {action_name}...")
        self._bus.emit(Events.UI_STATUS, status="processing")
        
        started = perf_counter()
        # --- Input Resolution ---
        diag.mark("input_resolve_start")
        input_text, image_base64, input_err = self._input_resolver.resolve(action)
        diag.mark("input_resolve_done")
        if input_text and not input_err:
            self._input_resolver.set_pipeline_root_if_needed(input_text)

        if input_err:
            print(f"[clipai] {input_err}")
            log_event({"event": "input_error", "action_id": action.get("id"), "error": input_err})
            notify("ClipAI", f"錯誤: {input_err}")
            self._bus.emit(Events.UI_STATUS, status="error")
            return

        safety_cfg = self._app_cfg.get("safety", {})
        safety_mode = safety_cfg.get("mode", "block")
        patterns = safety_cfg.get("patterns")
        safety_result = apply_safety(input_text, safety_mode, patterns)
        if safety_result["action"] == "block":
            hits = safety_result.get("hits", [])
            print(f"[clipai] Blocked: possible sensitive content detected. Patterns matched: {hits}")
            log_event({"event": "blocked", "action_id": action.get("id"), "hits": hits})
            notify("ClipAI", f"安全攔截：偵測到敏感資訊 {hits}，已停止處理。")
            self._bus.emit(Events.UI_STATUS, status="warning")
            return

        input_text = safety_result["text"]

        user_input = user_input_override or ""
        if not user_input and action.get("show_dialog", False):
            if self._pipeline.is_dialog_active():
                print(f"[clipai] Pipeline Mode: Intercepting dialog request for {action_name}")
                # In pipeline mode, do NOT open a new dialog — it would destroy
                # the existing popup window.  Proceed with empty user_input so
                # the action executes directly against the current pipeline content.
                user_input = ""
            else:
                time.sleep(0.2)
                user_input = get_user_input(
                    title=f"ClipAI - {action.get('name')}",
                    prompt_text=f"Enter additional context for '{action.get('name')}':"
                )
                if user_input is None:
                    print("[clipai] Action cancelled by user.")
                    self._bus.emit(Events.UI_STATUS, status="idle")
                    return

        if action.get("id") == "short_keep_meaning" and action.get("use_rewrite_options", False):
            if self._pipeline.is_dialog_active():
                print(f"[clipai] Pipeline Mode: Skipping rewrite options dialog for {action_name}")
                # In pipeline mode, skip the rewrite options dialog and proceed
                # with default (empty) user_input to avoid destroying the popup.
            else:
                time.sleep(0.2)
                options = get_rewrite_options()
                if options is None:
                    print("[clipai] Rewrite options cancelled by user.")
                    self._bus.emit(Events.UI_STATUS, status="idle")
                    return
                user_input = options

        resolved_cfg = self._action_service.resolve_config(action)

        messages = self._action_service.build_messages(
            action, input_text, user_input, resolved_cfg=resolved_cfg
        )

        # --- TTS Transform: Append prompt suffix for speech-friendly output ---
        if tts_output and should_use_full_transform(action):
            # Append TTS format override to the last user message
            for msg in reversed(messages):
                if msg["role"] == "user":
                    msg["content"] += TTS_PROMPT_SUFFIX
                    break

        output_cfg = action.get("output", {})
        copy_enabled = output_cfg.get("copy", True)
        show_popup = output_cfg.get("show_popup", False)

        # --- LLM Execution ---
        # TTS output mode forces non-streaming
        if tts_output:
            stream = False
        else:
            stream = show_popup or self._pipeline.is_dialog_active()
        diag.mark("llm_execute_start", stream=str(stream))
        try:
            result = self._action_service.execute(
                action, messages,
                image_base64=image_base64, stream=stream,
                resolved_cfg=resolved_cfg,
            )
            diag.mark("llm_execute_done", is_generator=str(not isinstance(result, str)))
        except Exception as e:
            print(f"[clipai] LLM call failed: {e}")
            log_event({"event": "llm_error", "action_id": action.get("id"), "error": str(e)})
            notify("ClipAI", f"錯誤: API 請求失敗或超時")
            self._bus.emit(Events.UI_STATUS, status="error")
            return

        if isinstance(result, str):
            memory_manager.memorize(
                content=result,
                content_type="ai_response",
                action_id=action.get("id"),
                original_input=input_text,
                is_manual=False
            )
            logger.debug(f"Raw LLM Result: '{result}' (len={len(result)})")

        # --- TTS Output Mode ---
        if tts_output and isinstance(result, str):
            self._output_router.route(result, action, input_text=input_text)
            self._maybe_show_tts_first_use_prompt()
            # Post-process: remove residual Markdown/emoji before TTS
            tts_text = sanitize_for_tts(result)
            self._tts_service.speak(tts_text)
            return

        # --- Popup / Pipeline handling ---
        if show_popup or self._pipeline.is_dialog_active():
            popup_text = self._handle_popup_result(
                result, action, input_text, user_input,
                image_base64, copy_enabled
            )
            if popup_text:
                result = popup_text

        # --- Output Routing ---
        if isinstance(result, str) and not show_popup and not self._pipeline.is_dialog_active():
            self._output_router.route(result, action, input_text=input_text)

        duration_ms = int((perf_counter() - started) * 1000)
        log_event({
            "event": "success",
            "action_id": action.get("id"),
            "action_name": action.get("name"),
            "model": resolved_cfg.model,
            "duration_ms": duration_ms,
            "input_len": len(input_text),
            "output_len": len(result) if isinstance(result, str) else 0,
        })

        if not show_popup:
            self._bus.emit(Events.UI_STATUS, status="success")

    def _handle_popup_result(self, result, action, input_text, user_input, 
                             image_base64, copy_enabled):
        """Handle result display via popup window."""
        action_name = action.get('name', 'Unknown')

        # Pipeline Mode
        if self._pipeline.is_dialog_active() and not (user_input and "Think Deep" in str(user_input)):
            if isinstance(result, str):
                full_text = result
            else:
                try:
                    full_text = "".join(list(result)).strip()
                except Exception as e:
                    logger.error(f"Pipeline mode LLM streaming failed: {e}")
                    notify("ClipAI", f"Pipeline 處理失敗: API 錯誤")
                    self._bus.emit(Events.UI_STATUS, status="error")
                    return None
                memory_manager.memorize(
                    content=full_text,
                    content_type="ai_response",
                    action_id=action.get("id"),
                    original_input=input_text,
                    is_manual=False
                )
                if copy_enabled:
                    write_clipboard_text(full_text)

            # Save undo point BEFORE updating content
            self._pipeline.save_undo_point()
            # Capture previous popup content = this round's input for context hint
            prev_content, _, _ = self._pipeline.get_popup_content()
            self._pipeline.set_popup_content(
                content=full_text,
                original_input=prev_content or input_text,
                action_id=action.get("id", "")
            )
            # Record the new transform in the chain
            self._pipeline.push_transform(action.get("name", "Unknown"))

            notify("ClipAI", f"Pipeline 處理完成: {action_name}")
            self._bus.emit(Events.UI_STATUS, status="success")
            return None

        # Normal popup mode
        self._pipeline.set_popup_content(
            content=result,
            original_input=input_text,
            action_id=action.get("id", "")
        )
        # Record initial transform for breadcrumb
        self._pipeline.push_transform(action.get("name", "Unknown"))

        history: List[Dict[str, str]] = []

        def on_think_deep_callback():
            deep_model = self._app_cfg.get("deep_model", "o4-mini-high")
            logger.info(f"Think Deep triggered. Model: {deep_model}")
            deep_action = action.copy()
            deep_action["model"] = deep_model

            deep_cfg = self._action_service.resolve_config(deep_action)
            messages = self._action_service.build_messages(
                deep_action, input_text, user_input,
                history=history, resolved_cfg=deep_cfg,
            )
            return self._action_service.execute(
                deep_action,
                messages,
                image_base64=image_base64,
                stream=True,
                resolved_cfg=deep_cfg,
            )

        # Resolve config once for follow-up requests (same action)
        follow_up_cfg = self._action_service.resolve_config(action)

        def _on_follow_up_request(text, action_id=None, assistant_text="", **kwargs):
            if not text:
                return
            if assistant_text:
                history.append({"role": "assistant", "content": assistant_text})
            history.append({"role": "user", "content": text})

            follow_messages = self._action_service.build_messages(
                action, input_text, user_input,
                history=history, resolved_cfg=follow_up_cfg,
            )
            follow_stream = self._action_service.execute(
                action,
                follow_messages,
                image_base64=image_base64,
                stream=True,
                resolved_cfg=follow_up_cfg,
            )
            self._pipeline.set_popup_content(
                content=follow_stream,
                original_input=input_text,
                action_id=action.get("id", "")
            )

        diag.mark("show_result_popup_call")
        with self._bus.scoped_subscription(Events.FOLLOW_UP_REQUEST, _on_follow_up_request):
            popup_result = show_result_popup(
                result,
                title=f"ClipAI - {action.get('name')}",
                original_input=input_text,
                tray=self._tray,
                on_think_deep_click=on_think_deep_callback,
                tts_service=self._tts_service,
                action_id=action.get("id", ""),
                follow_up_placeholder=action.get("follow_up_placeholder"),
            )
        full_text = popup_result.get("text", "")

        if not isinstance(result, str) and full_text:
            final_text = full_text
            if self._app_cfg.get("add_result_header", False):
                final_text = f"[{action.get('name')}]\n{final_text}"

            memory_manager.memorize(
                content=final_text,
                content_type="ai_response",
                action_id=action.get("id"),
                original_input=input_text,
                is_manual=False
            )

            if copy_enabled:
                self._output_router.copy_result(final_text)

            return final_text

        return full_text if full_text else (result if isinstance(result, str) else "")

    def _handle_memorize(self, action, comment=None, show_confirmation=True):
        """Memorize content from clipboard."""
        content = read_clipboard_text() or ""
        
        if not content.strip():
            notify("ClipAI", "沒有可記住的內容（剪貼簿為空）。")
            return

        memory_manager.memorize(
            content=content.strip(),
            content_type="clipboard",
            comment=comment,
            action_id=action.get("id"),
            is_manual=True
        )

        if show_confirmation:
            pinned_count = memory_manager.get_manual_count()
            preview = content.strip().replace("\n", " ")
            time.sleep(0.2)
            show_memory_confirmation(
                content_preview=preview,
                memory_count=pinned_count,
                max_count=10,
                on_undo=lambda: memory_manager.remove_last_manual_memory(),
            )
        else:
            notify("ClipAI", "已釘選剪貼簿內容 (Locked Memory)")

    def _handle_short_keep_meaning_long_press(self, action):
        """Handle long-press options for short_keep_meaning."""
        action = {**action, "use_rewrite_options": True}
        self.handle_action(action)

    def _handle_smart_qa_long_press(self, action):
        """Handle long-press behavior for smart_qa."""
        action = {**action, "show_dialog": True}
        self.handle_action(action)

    def _maybe_show_tts_first_use_prompt(self):
        """Show a one-time notification when TTS modifier is first used."""
        if self._app_cfg.get("_tts_modifier_prompted", False):
            return
        notify("🔊 TTS 模式", "提醒：TTS 模式會將 AI 結果唸出來。請注意周圍環境。")
        self._app_cfg["_tts_modifier_prompted"] = True


