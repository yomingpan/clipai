from __future__ import annotations

from ClipAI.core.models import EntryInputSourcePreview, PreparedInput


_PREVIEW_LIMIT = 90


def allows_entry_panel_clipboard_fallback(prepared: PreparedInput) -> bool:
    outcome = prepared.selection_outcome
    return (
        outcome is not None
        and outcome.status == 'unknown'
        and not outcome.needs_modifier_release
        and (prepared.clipboard_text_document is not None or prepared.clipboard_image is not None)
    )


def build_entry_input_preview(
    prepared: PreparedInput,
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
    if (
        prepared.selection_outcome is not None
        and prepared.selection_outcome.needs_modifier_release
        and not prepared.clipboard_override
    ):
        return EntryInputSourcePreview(
            'failed', '請先放開按鍵，再按重試。',
            clipboard_override_available=(
                prepared.clipboard_text_document is not None or prepared.clipboard_image is not None
            ),
        )
    if (
        prepared.selection_outcome is not None
        and prepared.selection_outcome.status in {"unknown", "cancelled"}
        and not prepared.clipboard_override
    ):
        return EntryInputSourcePreview(
            "failed", "這次未能確認反白內容。" + (" " + prepared.clipboard_preview() if prepared.clipboard_preview() else ""),
            clipboard_override_available=(
                prepared.clipboard_text_document is not None or prepared.clipboard_image is not None
            ),
        )
    if selection is not None and not prepared.clipboard_override:
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
