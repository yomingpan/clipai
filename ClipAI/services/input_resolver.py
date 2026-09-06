from __future__ import annotations

from ClipAI.core.errors import CancelledError, InputError, SelectionUnavailableError
from ClipAI.core.models import ExternalWindowRef, InputDocument, InputMode, PreparedInput, SelectionCaptureOutcome, SelectionCaptureRequest
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
        prepared = self._capture_input_facts(
            cancellation,
            request=request,
            probe_selection=mode == "selection_or_clipboard",
            read_image=True,
            read_text=mode != "clipboard_image",
        )
        return self._require_document(prepared, mode)

    def resolve_text(self, cancellation: CancellationToken | None = None, *, request: SelectionCaptureRequest | None = None) -> InputDocument:
        """Resolve text only: explicit selection first, then clipboard text."""
        prepared = self._capture_input_facts(
            cancellation,
            request=request,
            probe_selection=True,
            read_image=False,
            read_text=True,
        )
        return self._require_document(prepared, "selection_or_clipboard", text_only=True)

    def prepare_input(
        self,
        cancellation: CancellationToken | None = None,
        *,
        target: ExternalWindowRef | None = None,
        request: SelectionCaptureRequest | None = None,
        probe_selection: bool = True,
    ) -> PreparedInput:
        """Capture all supported external input facts once for later mode lookup."""

        return self._capture_input_facts(
            cancellation,
            target=target,
            request=request,
            probe_selection=probe_selection,
            read_image=True,
            read_text=True,
        )

    def _capture_input_facts(
        self,
        cancellation: CancellationToken | None,
        *,
        target: ExternalWindowRef | None = None,
        request: SelectionCaptureRequest | None = None,
        probe_selection: bool,
        read_image: bool,
        read_text: bool,
    ) -> PreparedInput:
        if cancellation is not None and cancellation.is_cancelled:
            raise CancelledError("Input capture was cancelled.")
        # Freeze fallbacks before compatibility copy can touch the clipboard.
        # Clipboard failures must not prevent a successful native selection read.
        image = None
        if read_image:
            try:
                image = self._clipboard.read_image()
            except Exception:
                pass
        clipboard_text = ""
        if read_text:
            try:
                clipboard_text = self._clipboard.read_text().strip()
            except Exception:
                pass
        outcome = (
            self._selection.capture(cancellation, target=target, request=request)
            if probe_selection and self._selection is not None
            else SelectionCaptureOutcome(
                status="unavailable",
                reason="selection_unavailable",
            )
        )
        if outcome.status == "cancelled" or (cancellation is not None and cancellation.is_cancelled):
            raise CancelledError("Input capture was cancelled.")
        selection_document = (
            InputDocument(outcome.text, "selection") if outcome.status == "selected" else None
        )
        return PreparedInput(
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
    def _require_document(
        prepared: PreparedInput,
        mode: InputMode,
        *,
        text_only: bool = False,
    ) -> InputDocument:
        resolution = prepared.resolve(mode)
        if resolution.document is not None:
            return resolution.document
        outcome = prepared.selection_outcome
        if resolution.unavailable_reason == "selection_unknown" and outcome is not None:
            raise SelectionUnavailableError(outcome.reason)
        if mode == "clipboard_image":
            raise InputError(
                "No screenshot found. Copy a screenshot to the clipboard, then trigger ClipAI again."
            )
        if text_only:
            raise InputError(
                "找不到文字。請先反白一段內容，或將文字複製到剪貼簿後再試一次。"
            )
        raise InputError("No text found. Select or copy text, then trigger ClipAI again.")
