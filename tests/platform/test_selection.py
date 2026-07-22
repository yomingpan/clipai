from __future__ import annotations

from ClipAI.core.models import ClipboardSnapshot, ImageContent
from ClipAI.platform.selection import SystemSelectionReader


class Clipboard:
    def __init__(self, value: str, image: ImageContent | None = None) -> None:
        self.value = value
        self.image = image
        self.writes: list[str] = []
        self.sequence = 1
        self.external_after_sequence: str | None = None

    def read_text(self) -> str:
        return self.value

    def write_text(self, text: str) -> None:
        self.value = text
        self.writes.append(text)
        self.sequence += 1

    def snapshot(self) -> ClipboardSnapshot:
        return ClipboardSnapshot(self.value, self.image)

    def sequence_number(self) -> int:
        sequence = self.sequence
        if self.external_after_sequence is not None:
            self.value = self.external_after_sequence
            self.sequence += 1
            self.external_after_sequence = None
        return sequence

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool:
        if self.sequence != expected_sequence:
            return False
        self.value = snapshot.text
        self.image = snapshot.image
        self.writes.append(snapshot.text)
        self.sequence += 1
        return True


def test_selection_capture_restores_original_clipboard() -> None:
    clipboard = Clipboard("original")

    def copy_selection() -> None:
        clipboard.value = "selected text"
        clipboard.sequence += 1

    reader = SystemSelectionReader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert reader.read_text() == "selected text"
    assert clipboard.value == "original"


def test_selection_capture_restores_original_non_text_content() -> None:
    image = ImageContent(b"png", "image/png")
    clipboard = Clipboard("", image)

    def copy_selection() -> None:
        clipboard.value = "selected text"
        clipboard.image = None
        clipboard.sequence += 1

    reader = SystemSelectionReader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert reader.read_text() == "selected text"
    assert clipboard.image == image


def test_selection_capture_waits_for_physical_hotkey_modifiers_to_be_released() -> None:
    clipboard = Clipboard("original")
    physical_modifiers = {"ctrl": True, "alt": True, "shift": False}
    checks = 0

    def modifier_is_pressed(modifier: str) -> bool:
        nonlocal checks
        checks += 1
        if checks > 3:
            physical_modifiers["ctrl"] = False
            physical_modifiers["alt"] = False
        return physical_modifiers[modifier]

    def copy_selection() -> None:
        if any(physical_modifiers.values()):
            return
        clipboard.value = "selected text"
        clipboard.sequence += 1

    reader = SystemSelectionReader(
        clipboard,
        copy_selection=copy_selection,
        modifier_is_pressed=modifier_is_pressed,
        modifier_release_timeout_sec=0.01,
        timeout_sec=0.01,
        poll_sec=0,
    )

    assert reader.read_text() == "selected text"
    assert clipboard.value == "original"


def test_selection_capture_does_not_copy_or_mutate_clipboard_when_modifiers_stay_pressed() -> None:
    clipboard = Clipboard("original")
    copy_calls = 0

    def copy_selection() -> None:
        nonlocal copy_calls
        copy_calls += 1

    reader = SystemSelectionReader(
        clipboard,
        copy_selection=copy_selection,
        modifier_is_pressed=lambda modifier: modifier == "alt",
        modifier_release_timeout_sec=0,
        timeout_sec=0.01,
        poll_sec=0,
    )

    assert reader.read_text() == ""
    assert copy_calls == 0
    assert clipboard.value == "original"
    assert clipboard.writes == []


def test_selection_capture_does_not_overwrite_later_external_clipboard_update() -> None:
    clipboard = Clipboard("original")

    def copy_selection() -> None:
        clipboard.value = "selected text"
        clipboard.sequence += 1
        clipboard.external_after_sequence = "external update"

    reader = SystemSelectionReader(clipboard, copy_selection=copy_selection, timeout_sec=0.01, poll_sec=0)
    assert reader.read_text() == ""
    assert clipboard.value == "external update"


def test_selection_capture_failure_falls_back_safely() -> None:
    clipboard = Clipboard("original")
    reader = SystemSelectionReader(
        clipboard,
        copy_selection=lambda: (_ for _ in ()).throw(RuntimeError("copy failed")),
        timeout_sec=0.01,
        poll_sec=0,
    )
    assert reader.read_text() == ""
    assert clipboard.value == "original"
