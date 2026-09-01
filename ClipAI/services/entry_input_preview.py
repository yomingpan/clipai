from __future__ import annotations

from ClipAI.core.models import EntryInputSourcePreview, PreparedEntryInput


_PREVIEW_LIMIT = 90


def build_entry_input_preview(
    prepared: PreparedEntryInput,
    *,
    workflow_selection: bool = False,
) -> EntryInputSourcePreview:
    workflow = prepared.workflow_document
    if workflow is not None:
        return EntryInputSourcePreview(
            "workflow_selection" if workflow_selection else "workflow_result",
            _compact(workflow.text),
        )
    selection = prepared.selection_document
    if selection is not None:
        return EntryInputSourcePreview("selection_text", _compact(selection.text))
    if prepared.clipboard_image is not None:
        return EntryInputSourcePreview("clipboard_image")
    clipboard = prepared.clipboard_text_document
    if clipboard is not None:
        return EntryInputSourcePreview("clipboard_text", _compact(clipboard.text))
    return EntryInputSourcePreview("failed", "找不到可用的選取內容或剪貼簿內容")


def _compact(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= _PREVIEW_LIMIT:
        return normalized
    return normalized[: _PREVIEW_LIMIT - 1].rstrip() + "…"
