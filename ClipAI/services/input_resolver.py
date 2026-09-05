from __future__ import annotations

from ClipAI.core.errors import CancelledError, InputError, SelectionUnavailableError
from ClipAI.core.models import ExternalWindowRef, InputDocument, InputMode, PreparedEntryInput, SelectionCaptureOutcome, SelectionCaptureRequest
from ClipAI.core.ports import ClipboardReader, SelectionReader
from ClipAI.core.state import CancellationToken


class InputResolver:
    def __init__(self, clipboard: ClipboardReader, selection: SelectionReader | None = None) -> None:
        self._clipboard = clipboard
        self._selection = selection

    def begin_selection(self, target: ExternalWindowRef | None = None) -> SelectionCaptureRequest:
        if self._selection is None:
            return SelectionCaptureRequest("unavailable", None)
        return self._selection.begin_capture(target)

    def resolve(self, mode: InputMode, cancellation: CancellationToken | None = None, *, request: SelectionCaptureRequest | None = None) -> InputDocument:
        if mode == "clipboard_image":
            image = self._clipboard.read_image()
            if image is None:
                raise InputError("No screenshot found. Copy a screenshot to the clipboard, then trigger ClipAI again.")
            return InputDocument(text="", source="screenshot", image=image)
        if mode == "selection_or_clipboard" and self._selection is not None:
            selected = self._selected_document(self._selection.capture(cancellation, request=request))
            if selected is not None:
                return selected
        image = self._clipboard.read_image()
        if image is not None:
            return InputDocument(text="", source="clipboard", image=image)
        clipboard_text = self._clipboard.read_text().strip()
        if not clipboard_text:
            raise InputError("No text found. Select or copy text, then trigger ClipAI again.")
        return InputDocument(text=clipboard_text, source="clipboard")

    def resolve_text(self, cancellation: CancellationToken | None = None, *, request: SelectionCaptureRequest | None = None) -> InputDocument:
        """Resolve text only: explicit selection first, then clipboard text."""
        if self._selection is not None:
            selected = self._selected_document(self._selection.capture(cancellation, request=request))
            if selected is not None:
                return selected
        clipboard_text = self._clipboard.read_text().strip()
        if not clipboard_text:
            raise InputError("找不到文字。請先反白一段內容，或將文字複製到剪貼簿後再試一次。")
        return InputDocument(text=clipboard_text, source="clipboard")

    def prepare_entry_input(
        self,
        cancellation: CancellationToken | None = None,
        *,
        target: ExternalWindowRef | None = None,
        request: SelectionCaptureRequest | None = None,
    ) -> PreparedEntryInput:
        """Capture all supported external input facts once for later mode lookup."""

        if cancellation is not None and cancellation.is_cancelled:
            raise CancelledError("Input capture was cancelled.")
        # Freeze the fallback before any compatibility copy can touch the clipboard.
        # A clipboard failure must not prevent a successful native selection read.
        try:
            image = self._clipboard.read_image()
        except Exception:
            image = None
        try:
            clipboard_text = self._clipboard.read_text().strip()
        except Exception:
            clipboard_text = ""
        outcome = (
            self._selection.capture(cancellation, target=target, request=request)
            if self._selection is not None
            else SelectionCaptureOutcome(reason="selection_unavailable")
        )
        if outcome.status == "cancelled" or (cancellation is not None and cancellation.is_cancelled):
            raise CancelledError("Input capture was cancelled.")
        selection_document = (
            InputDocument(outcome.text, "selection") if outcome.status == "selected" else None
        )
        return PreparedEntryInput(
            selection_document=selection_document,
            clipboard_text_document=(
                InputDocument(clipboard_text, "clipboard")
                if clipboard_text
                else None
            ),
            clipboard_image=image,
            selection_outcome=outcome,
        )

    @staticmethod
    def _selected_document(outcome: SelectionCaptureOutcome) -> InputDocument | None:
        if outcome.status == "cancelled":
            raise CancelledError("Input capture was cancelled.")
        if outcome.status == "unknown":
            raise SelectionUnavailableError(outcome.reason)
        if outcome.status == "selected":
            return InputDocument(outcome.text, "selection")
        return None
