from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
import uuid

import customtkinter as ctk

from ClipAI.core.commands import CloseProviderSettings, ControlSurfaceActivated, ControlSurfaceReleased, OpenProviderSettings, RefreshProviderModels, ValidateAndSaveProviderSettings
from ClipAI.core.models import ControlSurfaceRef, ModelCatalogConnection, ProviderOption, ProviderSettingsInput, ProviderSettingsState
from ClipAI.core.ports import NativeWindowSurface
from ClipAI.ui.window_icons import CUSTOMTKINTER_ICON_DELAY_MS, destroy_window_icons, install_clipai_window_icons


class ProviderSettingsDialog:
    """Toolkit-only editor that emits one typed save intent."""

    def __init__(self, master, command_sink: Callable[[object], None], native_window_surface: NativeWindowSurface) -> None:
        self._command_sink = command_sink
        self._native_window_surface = native_window_surface
        self._state: ProviderSettingsState | None = None
        self._loaded_provider = ""
        self._gateway_custom_mode = tk.BooleanVar(value=True)
        self._window = ctk.CTkToplevel(master)
        self._window.title("ClipAI Provider Settings")
        self._window_icon_handles: tuple[int, ...] = ()
        self._window.after(CUSTOMTKINTER_ICON_DELAY_MS, self._apply_windows_window_icons)
        self._window.geometry("430x500")
        self._window.minsize(390, 460)
        self._window.protocol("WM_DELETE_WINDOW", self._request_close)
        self._window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._window, text="Provider", anchor="w").grid(row=0, column=0, padx=24, pady=(22, 4), sticky="ew")
        self._provider = tk.StringVar()
        self._provider_menu = ctk.CTkOptionMenu(self._window, variable=self._provider, values=[""], command=self._provider_changed)
        self._provider_menu.grid(row=1, column=0, padx=24, sticky="ew")

        self._gateway_name = ctk.CTkEntry(self._window, placeholder_text="Server name")
        self._gateway_name.grid(row=2, column=0, padx=24, pady=(16, 4), sticky="ew")
        self._gateway_url = ctk.CTkEntry(self._window, placeholder_text="https://gateway.example/v1")
        self._gateway_url.grid(row=3, column=0, padx=24, pady=4, sticky="ew")

        self._credential_status = ctk.CTkLabel(self._window, text="", anchor="w")
        self._credential_status.grid(row=4, column=0, padx=24, pady=(16, 4), sticky="ew")
        self._api_key = ctk.CTkEntry(self._window, show="*", placeholder_text="Enter a new API key")
        self._api_key.grid(row=5, column=0, padx=24, sticky="ew")

        ctk.CTkLabel(self._window, text="Default model", anchor="w").grid(row=6, column=0, padx=24, pady=(16, 4), sticky="ew")
        self._model = tk.StringVar()
        self._model_menu = ctk.CTkOptionMenu(self._window, variable=self._model, values=[""])
        self._model_menu.grid(row=7, column=0, padx=24, sticky="ew")
        self._model_entry = ctk.CTkEntry(self._window, placeholder_text="Model ID")
        self._model_entry.grid(row=7, column=0, padx=24, sticky="ew")
        self._custom_model = ctk.CTkCheckBox(
            self._window,
            text="Use custom model ID",
            variable=self._gateway_custom_mode,
            command=self._gateway_model_mode_changed,
        )
        self._custom_model.grid(row=8, column=0, padx=24, pady=(6, 0), sticky="w")

        self._message = ctk.CTkLabel(self._window, text="", anchor="w", wraplength=380, justify="left")
        self._message.grid(row=9, column=0, padx=24, pady=(18, 8), sticky="ew")
        self._save = ctk.CTkButton(self._window, text="Validate and Save", command=self._submit)
        self._save.grid(row=10, column=0, padx=24, pady=(8, 12), sticky="ew")
        self._refresh = ctk.CTkButton(self._window, text="Refresh Models", command=self._refresh_models)
        self._refresh.grid(row=11, column=0, padx=24, pady=(0, 22), sticky="ew")
        self._window.bind("<Escape>", lambda _event: self._handle_escape())
        self._window.bind("<FocusIn>", lambda _event: self._command_sink(
            ControlSurfaceActivated(ControlSurfaceRef("provider-settings", "provider_settings"))
        ), add="+")
        self._window.bind("<FocusOut>", lambda _event: self._window.after(
            0, self._release_focus_if_outside
        ), add="+")
        self._window.bind("<Control-Return>", lambda _event: self._submit())

    def _handle_escape(self) -> str:
        return "break"

    def _request_close(self) -> None:
        self._command_sink(CloseProviderSettings())

    def _release_focus_if_outside(self) -> None:
        try:
            focused = self._window.focus_get()
            if focused is None or focused.winfo_toplevel() is not self._window:
                self._command_sink(ControlSurfaceReleased(
                    ControlSurfaceRef("provider-settings", "provider_settings")
                ))
        except tk.TclError:
            pass

    def apply(self, state: ProviderSettingsState) -> None:
        self._state = state
        provider_ids = [option.provider_id for option in state.providers]
        self._provider_menu.configure(values=provider_ids)
        provider_changed = self._loaded_provider != state.selected_provider
        self._provider.set(state.selected_provider)
        pending = state.operation_state == "pending"
        enabled = "disabled" if pending else "normal"
        self._provider_menu.configure(state="normal")
        self._model_menu.configure(state="normal")
        self._api_key.configure(state="normal")
        self._gateway_name.configure(state="normal")
        self._gateway_url.configure(state="normal")
        self._model_entry.configure(state="normal")
        if provider_changed:
            self._apply_provider(state.selected_provider, selected_model=state.selected_model, load_values=True)
            self._loaded_provider = state.selected_provider
        else:
            self._apply_provider(state.selected_provider, selected_model=state.selected_model, load_values=False)
            if state.operation_kind == "refresh" and state.operation_state == "succeeded":
                option = self._option(state.selected_provider)
                if option is not None and option.available_models:
                    self._model.set(state.selected_model if state.selected_model in option.available_models else option.available_models[0])
                self._gateway_custom_mode.set(False)
                self._gateway_model_mode_changed()
        self._provider_menu.configure(state=enabled)
        self._model_menu.configure(state=enabled)
        self._api_key.configure(state=enabled)
        self._gateway_name.configure(state=enabled)
        self._gateway_url.configure(state=enabled)
        self._model_entry.configure(state=enabled)
        self._save.configure(state=enabled, text="Validating..." if pending and state.operation_kind == "save" else "Validate and Save")
        self._refresh.configure(state=enabled, text="Refreshing..." if pending and state.operation_kind == "refresh" else "Refresh Models")
        self._message.configure(text=state.message)
        if state.operation_state == "succeeded":
            self._api_key.delete(0, "end")
        self._window.deiconify()
        self._window.lift()
        if not pending:
            self._api_key.focus_set()

    def _provider_changed(self, provider_id: str) -> None:
        self._api_key.delete(0, "end")
        self._apply_provider(provider_id, load_values=True)
        self._credential_status.configure(text="Loading saved credentials...")
        self._loaded_provider = ""
        self._command_sink(OpenProviderSettings(provider_id))

    def _apply_provider(self, provider_id: str, *, selected_model: str | None = None, load_values: bool = False) -> None:
        option = self._option(provider_id)
        if option is None:
            return
        models = option.available_models or (option.selected_model,)
        if option.capabilities.custom_endpoint:
            self._gateway_name.grid()
            self._gateway_url.grid()
            if load_values:
                self._replace_entry(self._gateway_name, self._state.connection_name if self._state else "")
                self._replace_entry(self._gateway_url, self._state.connection_base_url if self._state else "")
                self._replace_entry(self._model_entry, selected_model or option.selected_model)
            has_catalog = bool(option.available_models)
            self._custom_model.grid()
            if has_catalog:
                self._model_menu.configure(values=list(option.available_models))
                if load_values:
                    self._gateway_custom_mode.set((selected_model or option.selected_model) not in option.available_models)
                if not self._gateway_custom_mode.get():
                    self._model.set(selected_model if selected_model in option.available_models else option.selected_model)
            else:
                self._gateway_custom_mode.set(True)
            self._gateway_model_mode_changed()
        else:
            self._gateway_name.grid_remove()
            self._gateway_url.grid_remove()
            self._model_entry.grid_remove()
            self._custom_model.grid_remove()
            self._model_menu.grid()
            self._model_menu.configure(values=list(models))
            self._model.set(selected_model if selected_model in models else option.selected_model)
        if option.capabilities.credential_optional:
            status = _credential_status(option.credential_hint, optional=True)
        else:
            status = _credential_status(option.credential_hint) if option.configured else "API key is not configured."
        self._credential_status.configure(text=status)

    def _gateway_model_mode_changed(self) -> None:
        option = self._option(self._provider.get())
        if option is None or not option.capabilities.editable_model:
            return
        if self._gateway_custom_mode.get():
            self._model_menu.grid_remove()
            self._model_entry.grid()
        else:
            self._model_entry.grid_remove()
            self._model_menu.grid()

    def _selected_model(self, provider: str) -> str:
        option = self._option(provider)
        return self._model_entry.get().strip() if option and option.capabilities.editable_model and self._gateway_custom_mode.get() else self._model.get().strip()

    @staticmethod
    def _replace_entry(entry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    def _option(self, provider_id: str) -> ProviderOption | None:
        state = self._state
        return next((item for item in state.providers if item.provider_id == provider_id), None) if state else None

    def _submit(self) -> None:
        state = self._state
        if state is None or state.operation_state == "pending":
            return
        provider = self._provider.get()
        api_key = self._api_key.get().strip()
        option = self._option(provider)
        if not api_key and (option is None or (not option.configured and not option.capabilities.credential_optional)):
            self._message.configure(text="Enter an API key before saving.")
            return
        operation_id = uuid.uuid4().hex
        self._command_sink(
            ValidateAndSaveProviderSettings(
                settings=ProviderSettingsInput(
                    provider=provider,
                    model=self._selected_model(provider),
                    api_key=api_key,
                    connection_name=self._gateway_name.get().strip() if option and option.capabilities.custom_endpoint else "",
                    connection_base_url=self._gateway_url.get().strip() if option and option.capabilities.custom_endpoint else "",
                ),
                operation_id=operation_id,
            )
        )

    def _refresh_models(self) -> None:
        state = self._state
        if state is None or state.operation_state == "pending":
            return
        provider = self._provider.get()
        option = self._option(provider)
        connection = (
            ModelCatalogConnection(
                base_url=self._gateway_url.get().strip(),
                api_key=self._api_key.get().strip(),
                fallback_model=self._selected_model(provider),
            )
            if option and option.capabilities.custom_endpoint
            else None
        )
        self._command_sink(RefreshProviderModels(provider, uuid.uuid4().hex, connection))

    def close(self) -> None:
        try:
            self._window.withdraw()
        except tk.TclError:
            pass

    def _apply_windows_window_icons(self) -> None:
        try:
            self._window_icon_handles = install_clipai_window_icons(self._window, self._native_window_surface)
        except (OSError, tk.TclError):
            pass

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except tk.TclError:
            pass
        destroy_window_icons(self._native_window_surface, self._window_icon_handles)
        self._window_icon_handles = ()


def _credential_status(hint: str, *, optional: bool = False) -> str:
    if hint == "configured":
        saved = "API key is configured."
    elif hint:
        saved = f"Using saved API key ending in {hint[-4:]}."
    elif optional:
        return "API key is optional. No saved key is configured."
    else:
        return "API key is not configured."
    return f"{saved} Leave blank to keep it."
