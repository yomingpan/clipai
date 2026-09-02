from __future__ import annotations

from ClipAI.core.errors import InputError
from ClipAI.core.models import InputDocument, InputMode, PreparedEntryInput
from ClipAI.core.ports import ClipboardReader, SelectionReader
from ClipAI.core.state import CancellationToken


class InputResolver:
    def __init__(self, clipboard: ClipboardReader, selection: SelectionReader | None = None) -> None:
        self._clipboard = clipboard
        self._selection = selection

    def resolve(self, mode: InputMode, cancellation: CancellationToken | None = None) -> InputDocument:
        if mode == "clipboard_image":
            image = self._clipboard.read_image()
            if image is None:
                raise InputError("No screenshot found. Copy a screenshot to the clipboard, then trigger ClipAI again.")
            return InputDocument(text="", source="screenshot", image=image)
        if mode == "selection_or_clipboard" and self._selection is not None:
            selected = self._selection.read_text(cancellation).strip()
            if selected:
                return InputDocument(text=selected, source="selection")
        image = self._clipboard.read_image()
        if image is not None:
            return InputDocument(text="", source="clipboard", image=image)
        clipboard_text = self._clipboard.read_text().strip()
        if not clipboard_text:
            raise InputError("No text found. Select or copy text, then trigger ClipAI again.")
        return InputDocument(text=clipboard_text, source="clipboard")

    def resolve_text(self, cancellation: CancellationToken | None = None) -> InputDocument:
        """Resolve text only: explicit selection first, then clipboard text."""
        if self._selection is not None:
            selected = self._selection.read_text(cancellation).strip()
            if selected:
                return InputDocument(text=selected, source="selection")
        clipboard_text = self._clipboard.read_text().strip()
        if not clipboard_text:
            raise InputError("找不到文字。請先反白一段內容，或將文字複製到剪貼簿後再試一次。")
        return InputDocument(text=clipboard_text, source="clipboard")

    def prepare_entry_input(
        self,
        cancellation: CancellationToken | None = None,
    ) -> PreparedEntryInput:
        """Capture all supported external input facts once for later mode lookup."""

        selection_document: InputDocument | None = None
        if self._selection is not None:
            selected = self._selection.read_text(cancellation).strip()
            if selected:
                selection_document = InputDocument(selected, "selection")
        image = self._clipboard.read_image()
        clipboard_text = self._clipboard.read_text().strip()
        return PreparedEntryInput(
            selection_document=selection_document,
            clipboard_text_document=(
                InputDocument(clipboard_text, "clipboard")
                if clipboard_text
                else None
            ),
            clipboard_image=image,
        )
