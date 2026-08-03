from __future__ import annotations

from dataclasses import dataclass
import threading

import pytest

from ClipAI.core.errors import CancelledError, InputError
from ClipAI.core.models import PasteDispatchReceipt, PasteRequest, PasteTarget
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.paste_operation import PasteOperationCoordinator, PasteOperationInProgress


TARGET = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)


@dataclass(frozen=True)
class Snapshot:
    value: str


class Clipboard:
    def __init__(self) -> None:
        self.value = "original"
        self.sequence = 1
        self.transient_writes: list[str] = []
        self.snapshot_error: Exception | None = None
        self.sequence_error_after_write: Exception | None = None
        self.restore_error: Exception | None = None
        self.external_change = False

    def snapshot(self) -> Snapshot:
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return Snapshot(self.value)

    def read_text(self) -> str:
        return self.value

    def write_text(self, text: str) -> None:
        self.value = text
        self.sequence += 1

    def write_transient_text(self, text: str) -> None:
        self.value = text
        self.sequence += 1
        self.transient_writes.append(text)

    def sequence_number(self) -> int:
        if self.transient_writes and self.sequence_error_after_write is not None:
            raise self.sequence_error_after_write
        return self.sequence

    def restore_if_unchanged(self, snapshot: Snapshot, expected_sequence: int) -> bool:
        if self.restore_error is not None:
            raise self.restore_error
        if self.external_change:
            self.write_text("external")
            return False
        if self.sequence != expected_sequence:
            return False
        self.write_text(snapshot.value)
        return True


class Dispatcher:
    def __init__(self) -> None:
        self.calls = 0
        self.before_dispatch = None
        self.after_dispatch = None
        self.error: Exception | None = None
        self.dispatch_started: threading.Event | None = None
        self.release_dispatch: threading.Event | None = None

    def dispatch(self, target: PasteTarget, cancellation) -> PasteDispatchReceipt:
        assert target == TARGET
        if self.before_dispatch is not None:
            self.before_dispatch(cancellation)
        if cancellation.is_cancelled:
            raise CancelledError("Paste was cancelled before dispatch.")
        if self.error is not None:
            raise self.error
        if self.dispatch_started is not None:
            self.dispatch_started.set()
        if self.release_dispatch is not None:
            self.release_dispatch.wait(1)
        if cancellation.is_cancelled:
            raise CancelledError("Paste was cancelled before dispatch.")
        self.calls += 1
        if self.after_dispatch is not None:
            self.after_dispatch(cancellation)
        return PasteDispatchReceipt("dispatched_unconfirmed")


def request(operation_id: str = "paste-1", workflow_id: str = "workflow-1") -> PasteRequest:
    return PasteRequest(operation_id, workflow_id, "result", TARGET)


def coordinator(clipboard: Clipboard, dispatcher: Dispatcher) -> PasteOperationCoordinator:
    return PasteOperationCoordinator(
        clipboard_transactions=ClipboardTransactionCoordinator(clipboard),
        dispatcher=dispatcher,
    )


def test_preservation_failure_is_fail_closed_before_dispatch() -> None:
    clipboard = Clipboard()
    clipboard.snapshot_error = InputError("Clipboard cannot be completely preserved.")
    dispatcher = Dispatcher()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "failed"
    assert outcome.delivery == "not_dispatched"
    assert outcome.cleanup == "not_required"
    assert dispatcher.calls == 0
    assert clipboard.transient_writes == []
    assert clipboard.value == "original"


def test_normal_dispatch_is_reported_as_unconfirmed_and_restores_clipboard() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "dispatched_unconfirmed"
    assert outcome.delivery == "dispatched_unconfirmed"
    assert outcome.cleanup == "restored"
    assert dispatcher.calls == 1
    assert clipboard.transient_writes == ["result"]
    assert clipboard.value == "original"


def test_system_dispatch_keeps_transient_text_until_target_consumes_paste() -> None:
    clipboard = Clipboard()
    consumed = []
    dispatcher = SystemKeyboardOutput(
        modifier_is_pressed=lambda _modifier: False,
        wait=lambda _delay: consumed.append(clipboard.read_text()),
        paste_shortcut=lambda: None,
        target_is_valid=lambda _target: True,
        activate_target=lambda _target: True,
        target_is_foreground=lambda _target: True,
    )

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert (consumed, clipboard.value, outcome.state) == (
        ["result"],
        "original",
        "dispatched_unconfirmed",
    )


def test_cleanup_failure_preserves_dispatch_truth_and_does_not_become_failed() -> None:
    clipboard = Clipboard()
    clipboard.restore_error = OSError("restore failed")
    dispatcher = Dispatcher()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "cleanup_failed"
    assert outcome.delivery == "dispatched_unconfirmed"
    assert outcome.cleanup == "failed"
    assert dispatcher.calls == 1
    assert clipboard.value == "result"
    assert "may already be pasted" in outcome.message.lower()


def test_sequence_failure_after_mutation_never_dispatches_and_reports_cleanup_failure() -> None:
    clipboard = Clipboard()
    clipboard.sequence_error_after_write = OSError("sequence unavailable")
    dispatcher = Dispatcher()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "cleanup_failed"
    assert outcome.delivery == "not_dispatched"
    assert outcome.cleanup == "failed"
    assert dispatcher.calls == 0
    assert clipboard.value == "result"


def test_cancellation_before_run_has_no_clipboard_or_keyboard_side_effect() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()
    operation = coordinator(clipboard, dispatcher).create(request())
    operation.cancel()

    outcome = operation.run()

    assert outcome.state == "cancelled"
    assert outcome.delivery == "not_dispatched"
    assert clipboard.transient_writes == []
    assert dispatcher.calls == 0


def test_cancellation_at_dispatch_gate_restores_without_sending_keys() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()
    dispatcher.before_dispatch = lambda cancellation: cancellation.cancel()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "cancelled"
    assert outcome.delivery == "not_dispatched"
    assert outcome.cleanup == "restored"
    assert dispatcher.calls == 0
    assert clipboard.value == "original"


def test_cancellation_after_dispatch_never_erases_commit_truth() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()
    dispatcher.after_dispatch = lambda cancellation: cancellation.cancel()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "dispatched_unconfirmed"
    assert outcome.delivery == "dispatched_unconfirmed"
    assert dispatcher.calls == 1


def test_new_operation_is_rejected_until_older_operation_reaches_terminal_outcome() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()
    paste = coordinator(clipboard, dispatcher)
    older = paste.create(request("older"))

    with pytest.raises(PasteOperationInProgress, match="still in progress"):
        paste.create(request("newer"))

    older.cancel()
    older_outcome = older.run()
    newer = paste.create(request("newer"))
    newer_outcome = newer.run()

    assert older_outcome.state == "cancelled"
    assert newer_outcome.state == "dispatched_unconfirmed"
    assert dispatcher.calls == 1


def test_running_same_operation_twice_never_dispatches_twice() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()
    operation = coordinator(clipboard, dispatcher).create(request())

    first = operation.run()
    second = operation.run()

    assert second == first
    assert dispatcher.calls == 1


def test_running_operation_rejects_overlap_from_another_workflow() -> None:
    clipboard = Clipboard()
    dispatcher = Dispatcher()
    dispatcher.dispatch_started = threading.Event()
    dispatcher.release_dispatch = threading.Event()
    paste = coordinator(clipboard, dispatcher)
    operation = paste.create(request("older"))
    outcomes = []
    worker = threading.Thread(target=lambda: outcomes.append(operation.run()))
    worker.start()
    assert dispatcher.dispatch_started.wait(1)

    with pytest.raises(PasteOperationInProgress):
        paste.create(request("newer", "workflow-2"))

    dispatcher.release_dispatch.set()
    worker.join(1)
    assert outcomes[0].state == "dispatched_unconfirmed"
    assert dispatcher.calls == 1


def test_external_clipboard_change_is_not_overwritten_and_is_visible_in_outcome() -> None:
    clipboard = Clipboard()
    clipboard.external_change = True
    dispatcher = Dispatcher()

    outcome = coordinator(clipboard, dispatcher).create(request()).run()

    assert outcome.state == "dispatched_unconfirmed"
    assert outcome.cleanup == "external_change"
    assert clipboard.value == "external"
