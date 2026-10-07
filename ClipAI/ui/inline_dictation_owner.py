"""Single UI owner for Inline Dictation windows and interaction identity."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

from ClipAI.core.commands import CancelInlineDictation, ConfirmInlineDictation, CopyInlineDictation, DismissInlineDictationTerminal
from ClipAI.core.models import InlineDictationPlacement, InlineInputMode, PasteOutcome
from ClipAI.core.ports import DisplayMetricsReader, NativeWindowSurface
from ClipAI.core.voice import VoiceProjection
from ClipAI.ui.inline_dictation import InlineDictationWindow


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
        self._window: InlineDictationWindow | None = None

    def open_inline_dictation(self, interaction_id: str = "", mode: InlineInputMode = "choice", placement: InlineDictationPlacement = "cursor") -> None:
        previous = self._window
        if previous is not None:
            if previous.interaction_id == interaction_id:
                return
            previous.close()
            self._window = None
        window = InlineDictationWindow(
            self._root,
            on_confirm=lambda refine: self._command_sink(ConfirmInlineDictation(interaction_id, refine)),
            on_cancel=lambda: self._command_sink(CancelInlineDictation(interaction_id)),
            on_copy=lambda: self._command_sink(CopyInlineDictation(interaction_id)),
            native_window_surface=self._native_window_surface,
            display_metrics=self._display_metrics,
            interaction_id=interaction_id,
            mode=mode,
            placement=placement,
        )
        self._window = window
        window.show()

    def update_inline_dictation(self, projection: VoiceProjection) -> None:
        if self._window is not None:
            self._window.update(projection)

    def _matching(self, interaction_id: str) -> InlineDictationWindow | None:
        window = self._window
        return window if window is not None and window.interaction_id == interaction_id else None

    def present_inline_paste_outcome(self, interaction_id: str, outcome: PasteOutcome, text: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_paste_outcome(outcome, text)
            if outcome.state in {"dispatched_unconfirmed", "cancelled"}:
                self._root.after(3000, lambda: self._command_sink(DismissInlineDictationTerminal(interaction_id)))

    def present_inline_paste_pending(self, interaction_id: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_paste_pending()

    def present_inline_paste_cancelling(self, interaction_id: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_paste_cancelling()

    def present_inline_choice(self, interaction_id: str, text: str, allow_refine: bool = True, message: str = "") -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.present_choice(text, allow_refine, message)

    def present_inline_refining(self, interaction_id: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_refining()

    def present_inline_refinement_pending(self, interaction_id: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_refinement_pending()

    def present_inline_cancel_unconfirmed(self, interaction_id: str, text: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_cancel_unconfirmed(text)

    def present_inline_recovery(self, interaction_id: str, text: str, message: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_recovery(text, message)

    def present_inline_copy_state(self, interaction_id: str, state: str) -> None:
        window = self._matching(interaction_id)
        if window is not None:
            window.show_copy_state(state)

    def close_inline_dictation(self, *, flash_failure: bool = False, message: str = "", interaction_id: str = "") -> None:
        window = self._window
        if window is None or (interaction_id and window.interaction_id != interaction_id):
            return
        window.close(flash_failure=flash_failure, message=message)
        if not flash_failure:
            self._window = None
