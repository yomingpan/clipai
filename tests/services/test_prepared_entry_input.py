from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ClipAI.core.models import ImageContent, InputDocument, PreparedEntryInput
from ClipAI.services.input_resolver import InputResolver


class Clipboard:
    def __init__(self, *, text: str = "clipboard", image: ImageContent | None = None) -> None:
        self.text = text
        self.image = image
        self.text_reads = 0
        self.image_reads = 0

    def read_text(self) -> str:
        self.text_reads += 1
        return self.text

    def read_image(self) -> ImageContent | None:
        self.image_reads += 1
        return self.image


class Selection:
    def __init__(self, text: str = "selected") -> None:
        self.text = text
        self.reads = 0

    def read_text(self, _cancellation=None) -> str:
        self.reads += 1
        return self.text


def test_external_preparation_captures_each_input_fact_once() -> None:
    image = ImageContent(b"png", "image/png")
    clipboard = Clipboard(text="clipboard", image=image)
    selection = Selection("selected")

    prepared = InputResolver(clipboard, selection).prepare_entry_input()

    assert selection.reads == 1
    assert clipboard.text_reads == 1
    assert clipboard.image_reads == 1
    assert prepared.resolve("selection_or_clipboard").document == InputDocument(
        "selected", "selection"
    )
    assert prepared.resolve("clipboard").document == InputDocument(
        "", "clipboard", image=image
    )
    assert prepared.resolve("clipboard_image").document == InputDocument(
        "", "screenshot", image=image
    )


def test_prepared_input_never_rereads_changed_external_state() -> None:
    clipboard = Clipboard(text="captured clipboard")
    selection = Selection("captured selection")
    prepared = InputResolver(clipboard, selection).prepare_entry_input()
    clipboard.text = "changed clipboard"
    selection.text = "changed selection"

    first = prepared.resolve("selection_or_clipboard")
    second = prepared.resolve("clipboard")

    assert first.document == InputDocument("captured selection", "selection")
    assert second.document == InputDocument("captured clipboard", "clipboard")
    assert selection.reads == 1
    assert clipboard.text_reads == 1


def test_prepared_mode_priority_matches_existing_input_resolver() -> None:
    image = ImageContent(b"png", "image/png")
    prepared = InputResolver(
        Clipboard(text="clipboard", image=image),
        Selection(""),
    ).prepare_entry_input()

    assert prepared.resolve("selection_or_clipboard").document == InputDocument(
        "", "clipboard", image=image
    )
    assert prepared.resolve("clipboard").document == InputDocument(
        "", "clipboard", image=image
    )
    assert prepared.resolve("clipboard_image").document == InputDocument(
        "", "screenshot", image=image
    )


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("selection_or_clipboard", "selection_or_clipboard_unavailable"),
        ("clipboard", "clipboard_unavailable"),
        ("clipboard_image", "clipboard_image_unavailable"),
    ],
)
def test_prepared_input_reports_typed_mode_incompatibility(mode, reason) -> None:
    resolution = PreparedEntryInput().resolve(mode)

    assert resolution.document is None
    assert resolution.unavailable_reason == reason


def test_workflow_input_preserves_exact_lineage_for_every_mode() -> None:
    document = InputDocument(
        "selected result",
        "workflow_result",
        workflow_id="workflow-1",
        step_id="step-2",
    )
    prepared = PreparedEntryInput(workflow_document=document)

    for mode in ("selection_or_clipboard", "clipboard", "clipboard_image"):
        assert prepared.resolve(mode).document is document


def test_prepared_input_is_immutable_and_hides_sensitive_repr() -> None:
    prepared = PreparedEntryInput(
        selection_document=InputDocument("private text", "selection")
    )

    assert "private text" not in repr(prepared)
    with pytest.raises(FrozenInstanceError):
        prepared.selection_document = None  # type: ignore[misc]


def test_workflow_preparation_rejects_missing_or_mixed_lineage() -> None:
    with pytest.raises(ValueError, match="exact lineage"):
        PreparedEntryInput(
            workflow_document=InputDocument("result", "workflow_result")
        )
    with pytest.raises(ValueError, match="cannot contain external"):
        PreparedEntryInput(
            workflow_document=InputDocument(
                "result",
                "workflow_result",
                workflow_id="workflow-1",
                step_id="step-1",
            ),
            selection_document=InputDocument("selected", "selection"),
        )
