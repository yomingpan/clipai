from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time

from PIL import Image, ImageDraw

from ClipAI.core.models import ApplicationStatus, GuidancePreferences, ModelSelectionState, ProviderSelectionState, SpeechSpeed, SpeechSpeedState
from ClipAI.core.voice import VoiceCapabilityPhase, VoiceLanguage, VoiceProjection

logger = logging.getLogger("clipai.tray")
SHORTCUT_GUIDE_MENU_LABEL = "Keyboard Shortcuts..."
SPEECH_SPEED_LABELS: tuple[tuple[SpeechSpeed, str], ...] = (
    ("slow", "Slow"),
    ("normal", "Normal"),
    ("fast", "Fast"),
    ("super_fast", "Super Fast"),
)

STATUS_COLORS: dict[ApplicationStatus, tuple[int, int, int]] = {
    "idle": (0, 82, 184),
    "processing": (255, 140, 0),
    "success": (0, 176, 79),
    "warning": (255, 215, 0),
    "error": (232, 17, 35),
    "paused": (107, 107, 107),
}

STATUS_LABELS: dict[ApplicationStatus, str] = {
    "idle": "Ready",
    "processing": "Processing",
    "success": "Ready",
    "warning": "Needs attention",
    "error": "Needs attention",
    "paused": "Paused",
}


def create_tray_image(status: ApplicationStatus = "idle", *, memory_active: bool = False, size: int = 64) -> Image.Image:
    render_scale = 4
    width = height = size * render_scale
    scale = (size / 64.0) * render_scale
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    thickness = int(14 * scale)
    gap = int(10 * scale)
    offset = int(16 * scale)
    cx, cy = width // 2, height // 2

    if memory_active:
        radius = int(7 * scale)
        dot_x = int(width * 0.80)
        dot_y = cy + int(15 * scale)
        draw.ellipse(
            (dot_x - radius, dot_y - radius, dot_x + radius, dot_y + radius),
            fill=(218, 165, 32),
            outline=(139, 101, 8),
            width=max(1, int(scale)),
        )

    color = STATUS_COLORS[status]
    draw.line(
        ((cx - offset // 2 - gap, cy + int(20 * scale)), (cx - offset // 2 + gap, cy - int(20 * scale))),
        fill=color,
        width=thickness,
    )
    draw.line(
        ((cx + offset // 2 - gap, cy + int(15 * scale)), (cx + offset // 2 + gap, cy - int(15 * scale))),
        fill=color,
        width=thickness,
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


class TrayController:
    def __init__(
        self,
        on_exit: Callable[[], None],
        on_export_diagnostics: Callable[[], None] | None = None,
        on_show_last_error: Callable[[], None] | None = None,
        *,
        model_selection: ModelSelectionState | None = None,
        on_select_model: Callable[[str, str], None] | None = None,
        provider_selection: ProviderSelectionState | None = None,
        on_select_provider: Callable[[str], None] | None = None,
        on_reload_configuration: Callable[[], None] | None = None,
        on_open_provider_settings: Callable[[], None] | None = None,
        on_open_shortcut_guide: Callable[[], None] | None = None,
        on_refresh_models: Callable[[], None] | None = None,
        guidance_preferences: GuidancePreferences | None = None,
        on_set_first_use_hints: Callable[[bool], None] | None = None,
        on_reset_first_use_hints: Callable[[], None] | None = None,
        speech_speed: SpeechSpeedState | None = None,
        on_set_speech_speed: Callable[[SpeechSpeed], None] | None = None,
        voice: VoiceProjection | None = None,
        on_enable_voice: Callable[[], None] | None = None,
        on_disable_voice: Callable[[], None] | None = None,
        on_set_voice_language: Callable[[VoiceLanguage], None] | None = None,
    ) -> None:
        self._on_exit = on_exit
        self._on_export_diagnostics = on_export_diagnostics
        self._on_show_last_error = on_show_last_error
        self._model_selection = model_selection
        self._on_select_model = on_select_model
        self._provider_selection = provider_selection
        self._on_select_provider = on_select_provider
        self._on_reload_configuration = on_reload_configuration
        self._on_open_provider_settings = on_open_provider_settings
        self._on_open_shortcut_guide = on_open_shortcut_guide
        self._on_refresh_models = on_refresh_models
        self._guidance_preferences = guidance_preferences
        self._on_set_first_use_hints = on_set_first_use_hints
        self._on_reset_first_use_hints = on_reset_first_use_hints
        self._speech_speed = speech_speed
        self._on_set_speech_speed = on_set_speech_speed
        self._voice = voice
        self._on_enable_voice = on_enable_voice
        self._on_disable_voice = on_disable_voice
        self._on_set_voice_language = on_set_voice_language
        self._icon = None
        self._thread: threading.Thread | None = None
        self._status: ApplicationStatus = "idle"
        self._memory_active = False
        self._lock = threading.Lock()

    def start(self) -> None:
        import pystray

        def quit_app(icon, _item) -> None:
            icon.stop()
            self._on_exit()

        menu_items = [
            pystray.MenuItem(lambda _item: f"ClipAI — {STATUS_LABELS[self._status]}", None, enabled=False),
            pystray.MenuItem(lambda _item: self._configuration_summary(), None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        if self._on_open_provider_settings is not None:
            menu_items.append(pystray.MenuItem("Settings and Models...", lambda _icon, _item: self._on_open_provider_settings()))
        if self._on_open_shortcut_guide is not None:
            menu_items.append(pystray.MenuItem(SHORTCUT_GUIDE_MENU_LABEL, lambda _icon, _item: self._on_open_shortcut_guide()))
        speech_speed_menu = self._build_speech_speed_menu(pystray)
        if speech_speed_menu is not None:
            menu_items.append(speech_speed_menu)
            menu_items.append(pystray.Menu.SEPARATOR)
        voice_menu = self._build_voice_menu(pystray)
        if voice_menu is not None:
            menu_items.append(voice_menu)
            menu_items.append(pystray.Menu.SEPARATOR)
        guidance_menu = self._build_guidance_menu(pystray)
        if guidance_menu is not None:
            menu_items.append(guidance_menu)
        support_items = []
        if self._on_show_last_error is not None:
            support_items.append(pystray.MenuItem("Show Last Error", lambda _icon, _item: self._on_show_last_error()))
        if self._on_export_diagnostics is not None:
            support_items.append(pystray.MenuItem("Export Diagnostics", lambda _icon, _item: self._on_export_diagnostics()))
        if support_items:
            menu_items.append(pystray.MenuItem("Support and Diagnostics", pystray.Menu(*support_items)))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Quit ClipAI", quit_app))

        self._icon = pystray.Icon(
            "clipai",
            create_tray_image(self._status, memory_active=self._memory_active),
            self._tooltip(),
            menu=pystray.Menu(*menu_items),
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name="ClipAITray")
        self._thread.start()

    def _configuration_summary(self) -> str:
        provider = ""
        if self._provider_selection is not None:
            selected = next((item for item in self._provider_selection.providers if item.provider_id == self._provider_selection.selected_provider), None)
            provider = selected.display_name if selected is not None else self._provider_selection.selected_provider.title()
        model = self._model_selection.selected_model if self._model_selection is not None else ""
        return " · ".join(part for part in (provider, model) if part) or "No provider configured"

    def _tooltip(self) -> str:
        return f"ClipAI — {STATUS_LABELS[self._status]} · {self._configuration_summary()}"

    def _build_model_menu(self, pystray):
        selection = self._model_selection
        if selection is None or self._on_select_model is None:
            return None
        label = "Model (refreshing)..." if selection.refreshing else ("Model (updating)..." if selection.configuration_pending else (f"Model ({selection.pending_model})..." if selection.pending_model else f"Model: {selection.selected_model}"))
        items = tuple(
            pystray.MenuItem(
                f"{model} (custom/current)" if model in selection.custom_models else model,
                self._model_action(model),
                checked=lambda _item, chosen=model: self._model_selection is not None and self._model_selection.selected_model == chosen,
                enabled=lambda _item: self._model_selection is not None and self._model_selection.pending_model is None and not self._model_selection.refreshing and not self._model_selection.configuration_pending,
            )
            for model in selection.available_models
        )
        return pystray.MenuItem(label, pystray.Menu(*items))

    def _build_provider_menu(self, pystray):
        selection = self._provider_selection
        if selection is None or self._on_select_provider is None:
            return None
        label = "Provider (reloading)..." if selection.reloading else ("Provider (updating)..." if selection.configuration_pending else (f"Provider ({selection.pending_provider})..." if selection.pending_provider else f"Provider: {selection.selected_provider}"))
        items = tuple(
            pystray.MenuItem(
                option.display_name,
                self._provider_action(option.provider_id),
                checked=lambda _item, chosen=option.provider_id: self._provider_selection is not None and self._provider_selection.selected_provider == chosen,
                enabled=lambda _item, chosen=option.provider_id: self._provider_selection is not None and self._provider_selection.pending_provider is None and not self._provider_selection.reloading and not self._provider_selection.configuration_pending and chosen != self._provider_selection.selected_provider,
            )
            for option in selection.providers
        )
        return pystray.MenuItem(label, pystray.Menu(*items))

    def _build_guidance_menu(self, pystray):
        if self._guidance_preferences is None or self._on_set_first_use_hints is None or self._on_reset_first_use_hints is None:
            return None
        return pystray.MenuItem(
            "Usage Guidance",
            pystray.Menu(
                pystray.MenuItem(
                    "Show tips the first time each Recipe is used",
                    lambda _icon, _item: self._on_set_first_use_hints(not self._guidance_preferences.first_use_hints_enabled),
                    checked=lambda _item: self._guidance_preferences.first_use_hints_enabled,
                    enabled=lambda _item: not self._guidance_preferences.update_pending,
                ),
                pystray.MenuItem(
                    "Show All Tips Again",
                    lambda _icon, _item: self._on_reset_first_use_hints(),
                    enabled=lambda _item: not self._guidance_preferences.update_pending,
                ),
            ),
        )

    def _build_speech_speed_menu(self, pystray):
        if self._speech_speed is None or self._on_set_speech_speed is None:
            return None
        return pystray.MenuItem(
            lambda _item: self._speech_speed_label(),
            pystray.Menu(*(
                pystray.MenuItem(
                    label,
                    self._speech_speed_action(speed),
                    checked=lambda _item, chosen=speed: self._speech_speed is not None and self._speech_speed.selected_speed == chosen,
                    radio=True,
                    enabled=lambda _item, chosen=speed: (
                        self._speech_speed is not None
                        and self._speech_speed.available
                        and not self._speech_speed.update_pending
                        and self._speech_speed.selected_speed != chosen
                    ),
                )
                for speed, label in SPEECH_SPEED_LABELS
            )),
        )

    def _speech_speed_label(self) -> str:
        state = self._speech_speed
        if state is None:
            return "Speech Speed"
        if not state.available:
            return "Speech Speed (unavailable)"
        if state.pending_speed is not None:
            return "Speech Speed (saving...)"
        if state.selected_speed is None:
            return "Speech Speed (Custom)"
        return "Speech Speed"

    def _speech_speed_action(self, speed: SpeechSpeed):
        def select(_icon, _item) -> None:
            state = self._speech_speed
            if (
                state is None
                or self._on_set_speech_speed is None
                or not state.available
                or state.update_pending
                or state.selected_speed == speed
            ):
                return
            self._on_set_speech_speed(speed)

        return select

    def _build_voice_menu(self, pystray):
        if self._voice is None or self._on_enable_voice is None or self._on_disable_voice is None:
            return None
        voice = self._voice
        enabled = voice.capability is VoiceCapabilityPhase.READY
        pending = voice.capability in {VoiceCapabilityPhase.REQUESTING_PERMISSION, VoiceCapabilityPhase.DISABLING}
        language_items = ()
        if self._on_set_voice_language is not None:
            language_items = (
                pystray.MenuItem(
                    "Traditional Chinese (zh-TW)",
                    lambda _icon, _item: self._on_set_voice_language(VoiceLanguage("zh-TW")),
                    checked=lambda _item: self._voice is not None and self._voice.language == "zh-TW",
                    enabled=lambda _item: self._voice is not None and self._voice.capture_id is None,
                ),
                pystray.MenuItem(
                    "English (en-US)",
                    lambda _icon, _item: self._on_set_voice_language(VoiceLanguage("en-US")),
                    checked=lambda _item: self._voice is not None and self._voice.language == "en-US",
                    enabled=lambda _item: self._voice is not None and self._voice.capture_id is None,
                ),
            )
        menu_items = [
            pystray.MenuItem("Enable Voice Input", lambda _icon, _item: self._on_enable_voice(), enabled=lambda _item: not enabled and not pending),
            pystray.MenuItem("Disable Voice Input", lambda _icon, _item: self._on_disable_voice(), enabled=lambda _item: enabled and not pending),
        ]
        if language_items:
            menu_items.append(pystray.MenuItem("Language", pystray.Menu(*language_items)))
        return pystray.MenuItem(
            lambda _item: f"Voice Input ({voice.capability.value.replace('_', ' ')})",
            pystray.Menu(*menu_items),
        )

    def set_guidance_preferences(self, preferences: GuidancePreferences) -> None:
        self._guidance_preferences = preferences
        self._refresh_menu()

    def set_speech_speed(self, state: SpeechSpeedState) -> None:
        self._speech_speed = state
        self._refresh_menu()

    def set_voice_projection(self, projection: VoiceProjection) -> None:
        self._voice = projection
        self._refresh_menu()

    def _provider_action(self, provider: str):
        def select(_icon, _item) -> None:
            self._select_provider(provider)

        return select

    def _select_provider(self, provider: str) -> None:
        selection = self._provider_selection
        if selection is None or self._on_select_provider is None or selection.pending_provider is not None or selection.configuration_pending or provider == selection.selected_provider:
            return
        self._provider_selection = ProviderSelectionState(selection.providers, selection.selected_provider, provider)
        self._refresh_menu()
        self._on_select_provider(provider)

    def set_provider_selection(self, selection: ProviderSelectionState) -> None:
        self._provider_selection = selection
        self._refresh_menu()
        self._update_title()

    def _model_action(self, model: str):
        def select(_icon, _item) -> None:
            self._select_model(model)

        return select

    def _select_model(self, model: str) -> None:
        selection = self._model_selection
        if selection is None or self._on_select_model is None or selection.pending_model is not None or selection.configuration_pending or model == selection.selected_model:
            return
        self._model_selection = ModelSelectionState(selection.provider, selection.available_models, selection.selected_model, model)
        self._refresh_menu()
        self._on_select_model(selection.provider, model)

    def set_model_selection(self, selection: ModelSelectionState) -> None:
        self._model_selection = selection
        self._refresh_menu()
        self._update_title()

    def _refresh_menu(self) -> None:
        if self._icon is not None:
            self._icon.update_menu()

    def _run(self) -> None:
        try:
            self._icon.run()
        except Exception:
            logger.exception("Tray icon loop failed")

    def set_status(self, status: ApplicationStatus) -> None:
        self._status = status
        self._update_icon()
        self._refresh_menu()

    def set_memory_active(self, active: bool) -> None:
        self._memory_active = active
        self._update_icon()

    def notify(self, title: str, message: str) -> None:
        """Show a notification through ClipAI's existing tray icon.

        Using the active pystray icon avoids Plyer's separate Windows helper
        window, which Windows otherwise presents as an additional Python icon.
        """
        if self._icon is None:
            logger.warning("Cannot show notification before tray icon is ready")
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            logger.exception("Tray notification failed title=%s", title)

    def _update_icon(self) -> None:
        if self._icon is None:
            return
        with self._lock:
            try:
                self._icon.icon = create_tray_image(self._status, memory_active=self._memory_active)
            except OSError:
                try:
                    time.sleep(0.05)
                    self._icon.icon = create_tray_image(self._status, memory_active=self._memory_active)
                except Exception:
                    logger.exception("Tray icon update failed after retry")
            except Exception:
                logger.exception("Tray icon update failed")
        self._update_title()

    def _update_title(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.title = self._tooltip()
        except Exception:
            logger.exception("Tray title update failed")

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
        self._thread = None
