"""Single lifecycle owner for root-owned modal dialogs."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

from ClipAI.core.models import ManagedUpdatePresentation, PersonalStyleState, ProviderSettingsState, ShortcutGuideSnapshot
from ClipAI.core.ports import NativeWindowSurface
from ClipAI.core.voice import VoiceProjection
from ClipAI.ui.about import AboutDialog
from ClipAI.ui.personal_styles import PersonalStylesDialog
from ClipAI.ui.provider_settings import ProviderSettingsDialog
from ClipAI.ui.shortcut_guide import ShortcutGuideDialog
from ClipAI.ui.voice_setup import VoiceSetupDialog


class OwnedModalRegistry:
    def __init__(
        self, root: tk.Misc, command_sink: Callable[[object], None],
        native_window_surface: NativeWindowSurface | None,
        *, version: str, github_url: str,
    ) -> None:
        self._root = root
        self._command_sink = command_sink
        self._native_window_surface = native_window_surface
        self._version = version
        self._github_url = github_url
        self._managed_update = ManagedUpdatePresentation("unavailable", "僅 managed 安裝支援自動更新。", False)
        self._provider_settings_dialog: ProviderSettingsDialog | None = None
        self._personal_styles_dialog: PersonalStylesDialog | None = None
        self._shortcut_guide_dialog: ShortcutGuideDialog | None = None
        self._voice_setup_dialog: VoiceSetupDialog | None = None
        self._about_dialog: AboutDialog | None = None

    def show_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is None:
            if self._native_window_surface is None:
                return
            self._provider_settings_dialog = ProviderSettingsDialog(self._root, self._command_sink, self._native_window_surface)
        self._provider_settings_dialog.apply(state)

    def set_provider_settings(self, state: ProviderSettingsState) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.apply(state)

    def close_provider_settings(self) -> None:
        if self._provider_settings_dialog is not None:
            self._provider_settings_dialog.close()

    def show_personal_styles(self, state: PersonalStyleState) -> None:
        if self._personal_styles_dialog is None:
            if self._native_window_surface is None:
                return
            self._personal_styles_dialog = PersonalStylesDialog(self._root, self._command_sink, self._native_window_surface)
        self._personal_styles_dialog.apply(state)

    def set_personal_styles(self, state: PersonalStyleState) -> None:
        if self._personal_styles_dialog is not None:
            self._personal_styles_dialog.apply(state)

    def close_personal_styles(self) -> None:
        if self._personal_styles_dialog is not None:
            self._personal_styles_dialog.close()

    def show_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None:
        if self._shortcut_guide_dialog is None:
            if self._native_window_surface is None:
                return
            self._shortcut_guide_dialog = ShortcutGuideDialog(self._root, self._command_sink, self._native_window_surface)
        self._shortcut_guide_dialog.show(snapshot)

    def set_shortcut_guide(self, snapshot: ShortcutGuideSnapshot) -> None:
        if self._shortcut_guide_dialog is not None:
            self._shortcut_guide_dialog.apply(snapshot)

    def close_shortcut_guide(self) -> None:
        if self._shortcut_guide_dialog is not None:
            self._shortcut_guide_dialog.close()

    def show_voice_setup(self) -> None:
        if self._voice_setup_dialog is None:
            self._voice_setup_dialog = VoiceSetupDialog(self._root, self._command_sink)
        self._voice_setup_dialog.show()

    def close_voice_setup(self) -> None:
        if self._voice_setup_dialog is not None:
            self._voice_setup_dialog.close()

    def set_voice_projection(self, projection: VoiceProjection) -> None:
        if self._voice_setup_dialog is not None:
            self._voice_setup_dialog.set_voice_projection(projection)

    def show_about(self) -> None:
        if self._native_window_surface is None:
            return
        if self._about_dialog is None:
            self._about_dialog = AboutDialog(
                self._root, self._command_sink, self._native_window_surface,
                version=self._version, github_url=self._github_url, managed_update=self._managed_update,
            )

    def set_managed_update(self, state: ManagedUpdatePresentation) -> None:
        self._managed_update = state
        if self._about_dialog is not None:
            self._about_dialog.set_managed_update(state)

    def close_about(self) -> None:
        if self._about_dialog is not None:
            self._about_dialog.close()
            self._about_dialog = None

    def destroy(self) -> None:
        for name in ("_provider_settings_dialog", "_personal_styles_dialog", "_shortcut_guide_dialog"):
            dialog = getattr(self, name)
            if dialog is not None:
                dialog.destroy()
                setattr(self, name, None)
