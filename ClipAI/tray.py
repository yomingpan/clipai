
import threading
import time
import math
import pystray
from PIL import Image, ImageDraw
from clipai import notification, memory_manager

# Global state for markdown formatting
markdown_enabled = True

def create_image(status="idle", size=64):
    """Create a status-aware icon for ClipAI.
    Uses the 'AI Bolt' design with colors reflecting the current state.
    High-quality rendering with anti-aliasing.
    """
    # Render at 4x size for anti-aliasing
    render_scale = 4
    width = height = size * render_scale
    
    # Determine if we have locked (manual) memory
    has_manual = memory_manager.get_manual_count() > 0
    
    # Scale factor for dimensions
    scale_factor = (size / 64.0) * render_scale

    # Always use pure white background to preserve brand identity
    image = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    dc = ImageDraw.Draw(image)

    thickness = int(14 * scale_factor)
    gap = int(10 * scale_factor)
    offset = int(16 * scale_factor)
    cx, cy = width // 2, height // 2

    if has_manual:
        # Locked Memory: Small golden dot in the bottom-right corner
        dot_radius = int(7 * scale_factor)
        # Align height with the slashes for a neater look
        # cy + 15*scale_factor is the bottom of the right slash
        dot_center_x = int(width * 0.80)
        dot_center_y = cy + int(15 * scale_factor)
        
        # Draw the golden dot with a subtle dark outline for contrast on white
        dc.ellipse(
            [dot_center_x - dot_radius, dot_center_y - dot_radius,
             dot_center_x + dot_radius, dot_center_y + dot_radius],
            fill=(218, 165, 32), # Goldenrod #DAA520
            outline=(139, 101, 8), # Darker gold for outline
            width=int(1 * scale_factor)
        )

    # Status-based color mapping
    colors = {
        "idle": (0, 82, 184),       # Micron Blue
        "processing": (255, 140, 0), # Orange
        "success": (0, 176, 79),    # Green
        "error": (232, 17, 35),     # Red
        "warning": (255, 215, 0),   # Gold/Yellow for safety blocks
        "paused": (107, 107, 107)   # Gray
    }
    
    color = colors.get(status, colors["idle"])
    
    # Slash 1 (Left)
    s1_start = (cx - offset // 2 - gap, cy + int(20 * scale_factor))
    s1_end = (cx - offset // 2 + gap, cy - int(20 * scale_factor))
    
    # Slash 2 (Right)
    s2_start = (cx + offset // 2 - gap, cy + int(15 * scale_factor))
    s2_end = (cx + offset // 2 + gap, cy - int(15 * scale_factor))

    # Draw lines (Drawn AFTER the border to ensure maximum contrast)
    dc.line([s1_start, s1_end], fill=color, width=thickness)
    dc.line([s2_start, s2_end], fill=color, width=thickness)
    
    # Downsample with high-quality Lanczos filter for anti-aliasing
    return image.resize((size, size), Image.Resampling.LANCZOS)

class TrayIcon:
    def __init__(self, on_quit_callback, client=None, tts_engine=None, app_cfg=None, actions_list=None,
                 rhythm_mode_manager=None, rhythm_reporter=None):
        self.on_quit_callback = on_quit_callback
        self.client = client
        self.tts_engine = tts_engine
        self.app_cfg = app_cfg or {}
        self.actions_list = actions_list or []
        self.rhythm_mode_manager = rhythm_mode_manager
        self.rhythm_reporter = rhythm_reporter
        self.icon = None
        self._thread = None
        self._models = []
        self._status = "idle"
        self._glow_thread = None
        self._running = False
        self._status_reset_timer = None
        self._icon_lock = threading.Lock()
        self._refresh_models()

        # Subscribe to events
        from clipai.core.event_bus import get_event_bus, Events
        bus = get_event_bus()
        
        # Refresh menu when rhythm mode changes
        if self.rhythm_mode_manager:
            bus.subscribe(Events.RHYTHM_MODE_CHANGE, self._on_rhythm_mode_change)

        if self.rhythm_reporter:
            bus.subscribe(Events.ACTION_START, self._on_rhythm_data_refresh)
            bus.subscribe(Events.STREAM_COMPLETE, self._on_rhythm_data_refresh)
            
        # Refresh icon when memory changes
        bus.subscribe(Events.MEMORY_CHANGED, self._on_memory_changed)
        # React to UI status events
        bus.subscribe(Events.UI_STATUS, self._on_ui_status)

    def _refresh_models(self):
        """Fetch models from the client if available."""
        client = self.client
        if client and hasattr(client, "list_models"):
            # Run in a separate thread to avoid blocking the UI if the API is slow
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

        # TTS Language selection submenu (Moved to top)
        tts_engine = self.tts_engine
        if tts_engine:
            tts_items = []
            
            # Auto detect option
            tts_items.append(pystray.MenuItem(
                "Auto Detect",
                lambda icon, item: tts_engine.set_mode("auto"),
                checked=lambda item: getattr(tts_engine, "current_mode", "auto") == "auto"
            ))
            tts_items.append(pystray.Menu.SEPARATOR)
            
            # Specific language options (Ordered: ZH-TW, EN, JA)
            if hasattr(tts_engine, "VOICE_MAP"):
                # Define the desired order
                order = ["zh-tw", "en", "ja"]
                # Filter and order the keys based on what's actually in VOICE_MAP
                available_langs = [l for l in order if l in tts_engine.VOICE_MAP]
                
                for lang_code in available_langs:
                    def make_tts_callback(code):
                        return lambda icon, item: tts_engine.set_mode(code)
                    
                    tts_items.append(pystray.MenuItem(
                        lang_code.upper(),
                        make_tts_callback(lang_code),
                        checked=lambda item, lc=lang_code: getattr(tts_engine, "current_mode", "auto") == lc
                    ))
            
            tts_menu = pystray.Menu(*tts_items)
            menu_items.append(pystray.MenuItem("TTS Language", tts_menu))

        # Model selection submenu
        client = self.client
        if client and hasattr(client, "list_models"):
            model_items = []
            for model_id in self._models:
                def make_callback(m_id):
                    return lambda icon, item: self._set_model(m_id)
                
                model_items.append(pystray.MenuItem(
                    model_id,
                    make_callback(model_id),
                    checked=lambda item, m_id=model_id: getattr(client, "default_model", None) == m_id
                ))
            
            if not model_items:
                model_items.append(pystray.MenuItem("Loading models...", None, enabled=False))
            
            model_menu = pystray.Menu(*model_items)
            menu_items.append(pystray.MenuItem("Select Model", model_menu))
            menu_items.append(pystray.Menu.SEPARATOR)

        menu_items.append(pystray.MenuItem(
            "Turn on notifications",
            toggle_notifications,
            checked=lambda item: notification.enabled
        ))

        menu_items.append(pystray.MenuItem(
            "Restore clipboard after paste",
            toggle_restore_clipboard,
            checked=lambda item: self.app_cfg.get("output", {}).get("restore_clipboard_after_paste", False)
        ))
        
        menu_items.append(pystray.MenuItem(
            "Markdown Paste",
            toggle_markdown,
            checked=lambda item: markdown_enabled
        ))

        # Auto Memory TTL Submenu
        ttl_options = [0, 5, 10, 30]
        ttl_items = []
        for mins in ttl_options:
            label = "Off" if mins == 0 else f"{mins} Mins"
            def make_ttl_callback(m):
                return lambda icon, item: memory_manager.set_auto_memory_ttl(m)
            
            ttl_items.append(pystray.MenuItem(
                label,
                make_ttl_callback(mins),
                checked=lambda item, m=mins: memory_manager.get_auto_memory_ttl() == m
            ))
        
        menu_items.append(pystray.MenuItem("Auto Memory TTL", pystray.Menu(*ttl_items)))

        # Rhythm Mode submenu (Phase 13d)
        rmm = self.rhythm_mode_manager
        if rmm:
            rhythm_mode_items = []
            mode_options = [
                ("steer", "🧭 Steer — 守決策空間"),
                ("accelerate", "⚡ Accelerate — 放大已選方向"),
                ("scout", "🔭 Scout — 發散可能性"),
            ]
            for mode_key, mode_label in mode_options:
                def make_rhythm_callback(m):
                    return lambda icon, item: rmm.set_mode(m)

                rhythm_mode_items.append(pystray.MenuItem(
                    mode_label,
                    make_rhythm_callback(mode_key),
                    checked=lambda item, mk=mode_key: rmm.current_mode == mk
                ))

            rhythm_menu = pystray.Menu(*rhythm_mode_items)
            menu_items.append(pystray.MenuItem("Rhythm Mode", rhythm_menu))

        # Today's Rhythm report (0016)
        rr = self.rhythm_reporter
        if rr:
            summary = rr.get_today_summary()
            avg = rr.get_7day_average()
            trend = rr.get_trend()

            calls = summary["api_calls"]
            tokens = summary["tokens_out"]
            avg_calls = avg["avg_calls"]
            avg_tokens = avg["avg_tokens"]

            # Format token counts: 1234 → "~1.2k", 500 → "500"
            def _fmt_tokens(n):
                if n >= 1000:
                    return f"~{n / 1000:.1f}k"
                return str(n)

            rhythm_report_items = [
                pystray.MenuItem(
                    f"  {calls} calls | {_fmt_tokens(tokens)} tok",
                    None, enabled=False
                ),
                pystray.MenuItem(
                    f"  7d avg: {avg_calls} | {_fmt_tokens(avg_tokens)}",
                    None, enabled=False
                ),
                pystray.MenuItem(
                    f"  {trend} trend",
                    None, enabled=False
                ),
            ]

            rhythm_report_menu = pystray.Menu(*rhythm_report_items)
            menu_items.append(pystray.MenuItem("Today's Rhythm 📊", rhythm_report_menu))

        menu_items.append(pystray.Menu.SEPARATOR)

        menu_items.append(pystray.MenuItem(
            "Hotkey Guide",
            self._show_hotkey_guide
        ))

        menu_items.append(pystray.MenuItem(
            "End the program",
            self._on_quit
        ))

        return pystray.Menu(*menu_items)

    def _on_rhythm_data_refresh(self, **kwargs):
        """Refresh tray menu when rhythm data changes (action start or stream complete)."""
        if self.icon:
            try:
                self.icon.menu = self._create_menu()
            except Exception as e:
                print(f"[clipai] Tray menu refresh failed: {e}")

    def _on_rhythm_mode_change(self, mode=None, previous=None, **kwargs):
        """Refresh the tray menu when rhythm mode changes."""
        if self.icon:
            try:
                self.icon.menu = self._create_menu()
            except Exception as e:
                print(f"[clipai] Tray menu refresh failed: {e}")

    def _safe_update_icon(self, status=None):
        """Thread-safe icon update with retry on WinError 1402.

        Serialises all ``self.icon.icon`` mutations behind ``_icon_lock`` so
        that concurrent callers (Timer threads, event-bus subscribers, etc.)
        cannot race on the Win32 Shell_NotifyIcon / CreateIconIndirect calls
        that pystray performs internally.

        On transient ``OSError`` (e.g. ERROR_INVALID_CURSOR_HANDLE 1402) the
        method waits briefly and retries once, which is usually enough for the
        system tray to settle after an explorer.exe refresh.
        """
        if not self.icon:
            return
        if status is None:
            status = self._status
        with self._icon_lock:
            try:
                self.icon.icon = create_image(status)
            except OSError:
                # Retry once after a short delay — the handle may have been
                # transiently invalidated by a concurrent update or an
                # explorer.exe tray refresh.
                try:
                    time.sleep(0.05)
                    self.icon.icon = create_image(status)
                except Exception as e:
                    print(f"[clipai] Tray icon update failed after retry: {e}")
            except Exception as e:
                print(f"[clipai] Tray icon update failed: {e}")

    def _on_memory_changed(self, **kwargs):
        """Refresh the tray icon when memory state changes.
        
        Runs in a background thread to avoid blocking the event emitter
        (which may be the hotkey thread). See doc/lesson_learnt_ui_deadlock.md.
        """
        threading.Thread(target=self._safe_update_icon, daemon=True).start()

    def _on_ui_status(self, status, reset_after=None, **kwargs):
        """Update tray icon based on UI status events and handle auto-reset."""
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
            default_delays = {
                "success": 2.0,
                "error": 3.0,
                "warning": 3.0,
            }
            reset_after = default_delays.get(status)

        if reset_after:
            self._status_reset_timer = threading.Timer(
                reset_after,
                lambda: self.update_status("idle")
            )
            self._status_reset_timer.daemon = True
            self._status_reset_timer.start()

    def _set_model(self, model_id):
        if self.client:
            self.client.default_model = model_id
            notification.notify("ClipAI", f"Model switched to: {model_id}")

    def _show_hotkey_guide(self, icon, item):
        """Open the Hotkey Guide panel in a separate thread to avoid blocking the tray."""
        from clipai.dialog import show_hotkey_guide
        threading.Thread(target=show_hotkey_guide, args=(self.actions_list,), daemon=True).start()

    def _on_quit(self, icon, item):
        icon.stop()
        if self.on_quit_callback:
            self.on_quit_callback()

    def update_status(self, status):
        """Update the tray icon to reflect the current status."""
        self._status = status
        self._safe_update_icon(status)

    def run(self):
        """Run the tray icon in a separate thread."""
        self._running = True
        self.icon = pystray.Icon(
            "ClipAI",
            create_image("idle"),
            "ClipAI",
            self._create_menu()
        )
        
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the tray icon."""
        self._running = False
        if self.icon:
            self.icon.stop()



