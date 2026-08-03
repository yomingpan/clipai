from __future__ import annotations

from dataclasses import dataclass
import threading

from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator


@dataclass(frozen=True)
class Snapshot:
    value: str


class Clipboard:
    def __init__(self) -> None:
        self.value = "original"
        self.sequence = 1
        self.writes: list[str] = []

    def snapshot(self):
        return Snapshot(self.value)

    def read_text(self):
        return self.value

    def write_text(self, text):
        self.value = text
        self.sequence += 1
        self.writes.append(text)

    def write_transient_text(self, text):
        self.write_text(text)

    def sequence_number(self):
        return self.sequence

    def restore_if_unchanged(self, snapshot, expected_sequence):
        if self.sequence != expected_sequence:
            return False
        self.write_text(snapshot.value)
        return True


class SelectionAdapter:
    def __init__(self, clipboard: Clipboard, calls: list[str]) -> None:
        self.clipboard = clipboard
        self.calls = calls

    def modifier_is_pressed(self, _modifier):
        return False

    def copy_selection(self):
        self.calls.append("selection")
        self.clipboard.write_text("selected")


def test_selection_waits_for_active_paste_transaction_and_uses_same_owner() -> None:
    clipboard = Clipboard()
    coordinator = ClipboardTransactionCoordinator(clipboard)
    paste_active = threading.Event()
    release_paste = threading.Event()
    selected = []
    calls: list[str] = []

    def paste() -> None:
        def work() -> None:
            calls.append("paste")
            paste_active.set()
            release_paste.wait(1)

        coordinator.use_temporary_text("paste-1", "result", work)

    def capture() -> None:
        outcome = coordinator.capture_selection(
            "selection-1",
            SelectionAdapter(clipboard, calls),
            timeout_sec=0.01,
            poll_sec=0,
        )
        selected.append(outcome.text)

    paste_thread = threading.Thread(target=paste)
    selection_thread = threading.Thread(target=capture)
    paste_thread.start()
    assert paste_active.wait(1)
    selection_thread.start()
    assert calls == ["paste"]
    release_paste.set()
    paste_thread.join(1)
    selection_thread.join(1)

    assert calls == ["paste", "selection"]
    assert selected == ["selected"]
    assert clipboard.value == "original"


def test_external_clipboard_mutation_is_never_restored_over() -> None:
    clipboard = Clipboard()
    coordinator = ClipboardTransactionCoordinator(clipboard)
    def mutate() -> None:
        clipboard.write_text("external")
    outcome = coordinator.use_temporary_text("paste-1", "result", mutate)
    assert clipboard.value == "external"
    assert outcome.cleanup == "external_change"
