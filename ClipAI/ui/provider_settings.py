from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
import uuid

import customtkinter as ctk

from ClipAI.core.commands import ValidateAndSaveProviderSettings
from ClipAI.core.models import ProviderOption, ProviderSettingsState


class ProviderSettingsDialog:
    """Toolkit-only editor that emits one typed save intent."""

    def __init__(self, master, command_sink: Callable[[object], None]) -> None:
        self._command_sink = command_sink
        self._state: ProviderSettingsState | None = None
        self._window = ctk.CTkToplevel(master)
        self._window.title("ClipAI Provider Settings")
        self._window.geometry("430x390")
        self._window.minsize(390, 350)
        self._window.protocol("WM_DELETE_WINDOW", self.close)
        self._window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._window, text="Provider", anchor="w").grid(row=0, column=0, padx=24, pady=(22, 4), sticky="ew")
        self._provider = tk.StringVar()
        self._provider_menu = ctk.CTkOptionMenu(self._window, variable=self._provider, values=[""], command=self._provider_changed)
        self._provider_menu.grid(row=1, column=0, padx=24, sticky="ew")

        self._credential_status = ctk.CTkLabel(self._window, text="", anchor="w")
        self._credential_status.grid(row=2, column=0, padx=24, pady=(16, 4), sticky="ew")
        self._api_key = ctk.CTkEntry(self._window, show="*", placeholder_text="Enter a new API key")
        self._api_key.grid(row=3, column=0, padx=24, sticky="ew")

        ctk.CTkLabel(self._window, text="Default model", anchor="w").grid(row=4, column=0, padx=24, pady=(16, 4), sticky="ew")
        self._model = tk.StringVar()
        self._model_menu = ctk.CTkOptionMenu(self._window, variable=self._model, values=[""])
        self._model_menu.grid(row=5, column=0, padx=24, sticky="ew")

        self._message = ctk.CTkLabel(self._window, text="", anchor="w", wraplength=380, justify="left")
        self._message.grid(row=6, column=0, padx=24, pady=(18, 8), sticky="ew")
        self._save = ctk.CTkButton(self._window, text="Validate and Save", command=self._submit)
        self._save.grid(row=7, column=0, padx=24, pady=(8, 22), sticky="ew")
        self._window.bind("<Escape>", lambda _event: self.close())
        self._window.bind("<Control-Return>", lambda _event: self._submit())

    def apply(self, state: ProviderSettingsState) -> None:
        self._state = state
        provider_ids = [option.provider_id for option in state.providers]
        self._provider_menu.configure(values=provider_ids)
        self._provider.set(state.selected_provider)
        self._apply_provider(state.selected_provider, selected_model=state.selected_model)
        pending = state.operation_state == "pending"
        enabled = "disabled" if pending else "normal"
        self._provider_menu.configure(state=enabled)
        self._model_menu.configure(state=enabled)
        self._api_key.configure(state=enabled)
        self._save.configure(state=enabled, text="Validating..." if pending else "Validate and Save")
        self._message.configure(text=state.message)
        if state.operation_state == "succeeded":
            self._api_key.delete(0, "end")
        self._window.deiconify()
        self._window.lift()
        if not pending:
            self._api_key.focus_set()

    def _provider_changed(self, provider_id: str) -> None:
        self._apply_provider(provider_id)

    def _apply_provider(self, provider_id: str, *, selected_model: str | None = None) -> None:
        option = self._option(provider_id)
        if option is None:
            return
        models = option.available_models or (option.selected_model,)
        self._model_menu.configure(values=list(models))
        self._model.set(selected_model if selected_model in models else option.selected_model)
        status = "API key is configured. Enter a new key to replace it." if option.configured else "API key is not configured."
        self._credential_status.configure(text=status)

    def _option(self, provider_id: str) -> ProviderOption | None:
        state = self._state
        return next((item for item in state.providers if item.provider_id == provider_id), None) if state else None

    def _submit(self) -> None:
        state = self._state
        if state is None or state.operation_state == "pending":
            return
        api_key = self._api_key.get().strip()
        if not api_key:
            self._message.configure(text="Enter a new API key before saving.")
            return
        operation_id = uuid.uuid4().hex
        self._command_sink(
            ValidateAndSaveProviderSettings(
                provider=self._provider.get(),
                model=self._model.get(),
                api_key=api_key,
                operation_id=operation_id,
            )
        )

    def close(self) -> None:
        try:
            self._window.withdraw()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except tk.TclError:
            pass
