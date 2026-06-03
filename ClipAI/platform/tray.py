import threading
import time
import logging

import pystray
from PIL import Image, ImageDraw

from clipai import memory_manager
from clipai.platform import notification

# Global state for markdown formatting
markdown_enabled = True
logger = logging.getLogger("clipai.tray")


def create_image(status="idle", size=64):
    """Create a status-aware icon for ClipAI."""
    render_scale = 4
    width = height = size * render_scale
    has_manual = memory_manager.get_manual_count() > 0
    scale_factor = (size / 64.0) * render_scale

    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    dc = ImageDraw.Draw(image)
    thickness = int(14 * scale_factor)
    gap = int(10 * scale_factor)
    offset = int(16 * scale_factor)
    cx, cy = width // 2, height // 2

    if has_manual:
        dot_radius = int(7 * scale_factor)
        dot_center_x = int(width * 0.80)
        dot_center_y = cy + int(15 * scale_factor)
        dc.ellipse(
            [
                dot_center_x - dot_radius,
                dot_center_y - dot_radius,
                dot_center_x + dot_radius,
                dot_center_y + dot_radius,
            ],
            fill=(218, 165, 32),
            outline=(139, 101, 8),
            width=int(1 * scale_factor),
        )

    colors = {
        "idle": (0, 82, 184),
        "processing": (255, 140, 0),
        "success": (0, 176, 79),
        "error": (232, 17, 35),
        "warning": (255, 215, 0),
        "paused": (107, 107, 107),
    }
    color = colors.get(status, colors["idle"])

    s1_start = (cx - offset // 2 - gap, cy + int(20 * scale_factor))
    s1_end = (cx - offset // 2 + gap, cy - int(20 * scale_factor))
    s2_start = (cx + offset // 2 - gap, cy + int(15 * scale_factor))
    s2_end = (cx + offset // 2 + gap, cy - int(15 * scale_factor))

    dc.line([s1_start, s1_end], fill=color, width=thickness)
    dc.line([s2_start, s2_end], fill=color, width=thickness)
    return image.resize((size, size), Image.Resampling.LANCZOS)


class TrayIcon:
    def __init__(self, on_quit_callback, client=None, tts_engine=None, app_cfg=None, actions_list=None):
        self.on_quit_callback = on_quit_callback
        self.client = client
        self.tts_engine = tts_engine
        self.app_cfg = app_cfg or {}
        self.actions_list = actions_list or []
        self.icon = None
        self._thread = None
        self._models = []
        self._status = "idle"
        self._running = False
        self._status_reset_timer = None
        self._icon_lock = threading.Lock()
        self._refresh_models()

        from clipai.core.event_bus import Events, get_event_bus

        bus = get_event_bus()
        bus.subscribe(Events.MEMORY_CHANGED, self._on_memory_changed)
        bus.subscribe(Events.UI_STATUS, self._on_ui_status)
        bus.subscribe(Events.TTS_STATE, self._on_tts_state)

    def _refresh_models(self):
        client = self.client
        if client and hasattr(client, "list_models"):
            def fetch():
                models = client.list_models()
                if models:
                    self._models = models
                    if self.icon:
                        self.icon.menu = self._create_menu()

            threading.Thread(target=fetch, daemon=True).start()

    def _create_menu(self):
        def toggle_notifications(icon, item):
            notification.enabled = not notification.enabled

        def toggle_restore_clipboard(icon, item):
            output_cfg = self.app_cfg.setdefault("output", {})
            current = output_cfg.get("restore_clipboard_after_paste", False)
            output_cfg["restore_clipboard_after_paste"] = not current

        def toggle_markdown(icon, item):
            global markdown_enabled
            markdown_enabled = not markdown_enabled

        menu_items = []

        tts_engine = self.tts_engine
        if tts_engine:
            tts_items = [
                pystray.MenuItem(
                    "Auto Detect",
                    lambda icon, item: tts_engine.set_mode("auto"),
                    checked=lambda item: getattr(tts_engine, "current_mode", "auto") == "auto",
                ),
                pystray.Menu.SEPARATOR,
            ]
            if hasattr(tts_engine, "VOICE_MAP"):
                for lang_code in [code for code in ("zh-tw", "en", "ja") if code in tts_engine.VOICE_MAP]:
                    def make_tts_callback(code):
                        return lambda icon, item: tts_engine.set_mode(code)

                    tts_items.append(
                        pystray.MenuItem(
                            lang_code.upper(),
                            make_tts_callback(lang_code),
                            checked=lambda item, lc=lang_code: getattr(tts_engine, "current_mode", "auto") == lc,
                        )
                    )

            menu_items.append(pystray.MenuItem("TTS Language", pystray.Menu(*tts_items)))

        client = self.client
        if client and hasattr(client, "list_models"):
            model_items = []
            for model_id in self._models:
                def make_callback(m_id):
                    return lambda icon, item: self._set_model(m_id)

                model_items.append(
                    pystray.MenuItem(
                        model_id,
                        make_callback(model_id),
                        checked=lambda item, m_id=model_id: getattr(client, "default_model", None) == m_id,
                    )
                )

            if not model_items:
                model_items.append(pystray.MenuItem("Loading models...", None, enabled=False))

            menu_items.append(pystray.MenuItem("Select Model", pystray.Menu(*model_items)))
            menu_items.append(pystray.Menu.SEPARATOR)

        menu_items.append(
            pystray.MenuItem(
                "Turn on notifications",
                toggle_notifications,
                checked=lambda item: notification.enabled,
            )
        )
        menu_items.append(
            pystray.MenuItem(
                "Restore clipboard after paste",
                toggle_restore_clipboard,
                checked=lambda item: self.app_cfg.get("output", {}).get("restore_clipboard_after_paste", False),
            )
        )
        menu_items.append(
            pystray.MenuItem(
                "Markdown Paste",
                toggle_markdown,
                checked=lambda item: markdown_enabled,
            )
        )

        ttl_items = []
        for mins in [0, 5, 10, 30]:
            label = "Off" if mins == 0 else f"{mins} Mins"

            def make_ttl_callback(m):
                return lambda icon, item: memory_manager.set_auto_memory_ttl(m)

            ttl_items.append(
                pystray.MenuItem(
                    label,
                    make_ttl_callback(mins),
                    checked=lambda item, m=mins: memory_manager.get_auto_memory_ttl() == m,
                )
            )

        menu_items.append(pystray.MenuItem("Auto Memory TTL", pystray.Menu(*ttl_items)))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Hotkey Guide", self._show_hotkey_guide))
        menu_items.append(pystray.MenuItem("End the program", self._on_quit))
        return pystray.Menu(*menu_items)

    def _safe_update_icon(self, status=None):
        if not self.icon:
            return
        if status is None:
            status = self._status
        with self._icon_lock:
            try:
                self.icon.icon = create_image(status)
            except OSError:
                try:
                    time.sleep(0.05)
                    self.icon.icon = create_image(status)
                except Exception as exc:
                    print(f"[clipai] Tray icon update failed after retry: {exc}")
            except Exception as exc:
                print(f"[clipai] Tray icon update failed: {exc}")

    def _on_memory_changed(self, payload=None, **kwargs):
        if isinstance(payload, dict):
            kwargs = {**payload, **kwargs}
        threading.Thread(target=self._safe_update_icon, daemon=True).start()

    def _on_ui_status(self, payload=None, status=None, reset_after=None, **kwargs):
        if isinstance(payload, dict):
            status = payload.get("status", status)
            reset_after = payload.get("reset_after", reset_after)
            kwargs = {**payload, **kwargs}
        if status is None:
            status = "idle"
        self.update_status(status)

        if self._status_reset_timer:
            try:
                self._status_reset_timer.cancel()
            except Exception:
                pass
            self._status_reset_timer = None

        if status == "idle":
            return

        if reset_after is None:
            default_delays = {"success": 2.0, "error": 3.0, "warning": 3.0}
            reset_after = default_delays.get(status)

        if reset_after:
            self._status_reset_timer = threading.Timer(reset_after, lambda: self.update_status("idle"))
            self._status_reset_timer.daemon = True
            self._status_reset_timer.start()

    def _on_tts_state(self, payload=None, phase=None, is_speaking=None, **kwargs):
        if isinstance(payload, dict):
            phase = payload.get("phase", phase)
            is_speaking = payload.get("is_speaking", is_speaking)
            kwargs = {**payload, **kwargs}
        del kwargs
        normalized = str(phase or "").strip().lower()
        if normalized in {"requesting", "buffering"}:
            self._on_ui_status(status="processing", reset_after=0)
            return
        if normalized == "start":
            self._on_ui_status(status="success", reset_after=0)
            return
        if normalized in {"stop", "end"}:
            self._on_ui_status(status="idle", reset_after=0)
            return
        if normalized == "error":
            self._on_ui_status(status="error")
            return
        if is_speaking:
            self._on_ui_status(status="processing", reset_after=0)

    def _set_model(self, model_id):
        if self.client:
            self.client.default_model = model_id
            notification.notify("ClipAI", f"Model switched to: {model_id}")

    def _show_hotkey_guide(self, icon, item):
        from clipai.ui.dialogs.hotkey_guide_dialog import show_hotkey_guide

        threading.Thread(
            target=show_hotkey_guide,
            args=(self.actions_list,),
            kwargs={"modifier_mode": str(self.app_cfg.get("hotkey_modifier_mode") or "ctrl_alt")},
            daemon=True,
        ).start()

    def _on_quit(self, icon, item):
        icon.stop()
        if self.on_quit_callback:
            self.on_quit_callback()

    def update_status(self, status):
        self._status = status
        self._safe_update_icon(status)

    def _run_icon_loop(self):
        if self.icon is None:
            return
        try:
            logger.info("[clipai] Tray icon loop starting.")
            self.icon.run(self._on_icon_ready)
            logger.info("[clipai] Tray icon loop stopped.")
        except Exception:
            logger.exception("[clipai] Tray icon loop failed.")
            raise

    def _on_icon_ready(self, icon):
        try:
            logger.info("[clipai] Tray icon setup ready; requesting visible icon.")
            icon.visible = True
            logger.info("[clipai] Tray icon visible=%s", icon.visible)
        except Exception:
            logger.exception("[clipai] Tray icon setup failed.")
            raise

    def run(self, *, detached: bool = True):
        self._running = True
        self.icon = pystray.Icon("ClipAI", create_image("idle"), "ClipAI", self._create_menu())
        if detached:
            self._thread = threading.Thread(target=self._run_icon_loop, daemon=True, name="ClipAITray")
            self._thread.start()
            return
        self._thread = threading.current_thread()
        self._run_icon_loop()

    def stop(self):
        self._running = False
        if self.icon:
            self.icon.stop()
