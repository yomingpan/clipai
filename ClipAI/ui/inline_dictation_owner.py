"""Single UI owner for Inline Dictation windows and interaction identity."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

from ClipAI.core.commands import CancelInlineDictation, ConfirmInlineDictation, CopyInlineDictation, DismissInlineDictationTerminal
from ClipAI.core.models import InlineInputMode
from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface
from ClipAI.core.voice import InlineDictationView
from ClipAI.ui.inline_pill import InlinePill


class InlineDictationInterfaceOwner:
    def __init__(
        self, root: tk.Misc, command_sink: Callable[[object], None], *,
        native_window_surface: NativeWindowSurface | None = None,
        display_metrics: DisplayMetricsReader | None = None,
    ) -> None:
        self._root = root
        self._command_sink = command_sink
        self._native_window_surface = native_window_surface
        self._display_metrics = display_metrics
        self._window: InlinePill | None = None
        self._close_job: str | None = None
        self._dismiss_job: str | None = None
        self._dismiss_for: str | None = None

    def open_inline_dictation(self, interaction_id: str = "", mode: InlineInputMode = "choice") -> None:
        if self._window is not None and self._window.interaction_id == interaction_id:
            return
        self.close_inline_dictation()
        window = InlinePill(
            self._root,
            on_confirm=lambda refine: self._command_sink(ConfirmInlineDictation(interaction_id, refine)),
            on_cancel=lambda: self._command_sink(CancelInlineDictation(interaction_id)),
            on_copy=lambda: self._command_sink(CopyInlineDictation(interaction_id)),
            native_window_surface=self._native_window_surface,
            display_metrics=self._display_metrics,
            interaction_id=interaction_id,
        )
        self._window = window
        window.show()

    def present_inline_dictation(self, view: InlineDictationView) -> None:
        window = self._window
        if window is None or window.interaction_id != view.interaction_id:
            return
        if view.phase == "closed":
            if view.message:
                window.present(view)
                if self._close_job is None:
                    self._close_job = self._root.after(3000, lambda: self._close_matching(window))
            else:
                self.close_inline_dictation(interaction_id=view.interaction_id)
            return
        window.present(view)
        if view.phase == "settled" and view.paste_outcome is not None and self._dismiss_for != view.interaction_id:
            delay = {"dispatched_unconfirmed": 600, "cancelled": 1200}.get(view.paste_outcome.state)
            if delay is not None:
                self._dismiss_for = view.interaction_id
                self._dismiss_job = self._root.after(delay, lambda: self._dismiss_matching(window))

    def _dismiss_matching(self, window: InlinePill) -> None:
        if self._window is window:
            self._dismiss_job = None
            self._command_sink(DismissInlineDictationTerminal(window.interaction_id))

    def _close_matching(self, window: InlinePill) -> None:
        if self._window is window:
            self._close_job = None
            self.close_inline_dictation(interaction_id=window.interaction_id)

    def close_inline_dictation(self, *, interaction_id: str = "") -> None:
        window = self._window
        if window is None or interaction_id and window.interaction_id != interaction_id:
            return
        for job in (self._close_job, self._dismiss_job):
            if job is not None:
                self._root.after_cancel(job)
        self._close_job = self._dismiss_job = None
        self._dismiss_for = None
        self._window = None
        window.close()
