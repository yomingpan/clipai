from __future__ import annotations

import pytest

from ClipAI.core.models import OutputOperationIntent, OutputOperationResult, PasteOutcome
from ClipAI.services.output_operation import OutputOperationCoordinator, paste_outcome_result
from ClipAI.services.user_control import UserControlCoordinator


class Presenter:
    def __init__(self) -> None:
        self.results = []

    def present_output_operation(self, result) -> None:
        self.results.append(result)


def test_operation_projects_pending_then_success() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("op", "workflow", "copy", "text")
    coordinator.begin(intent)
    coordinator.settle(OutputOperationResult("op", "workflow", "copy", "succeeded"))
    assert [result.state for result in presenter.results] == ["pending", "succeeded"]


def test_failure_is_visible_and_carries_user_facing_error() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("op", "workflow", "paste", "text")
    coordinator.begin(intent)
    coordinator.fail(intent, RuntimeError("paste failed"))
    assert presenter.results[-1].state == "failed"
    assert presenter.results[-1].error.message == "paste failed"


def test_late_completion_cannot_replace_newer_same_kind_operation() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    old = OutputOperationIntent("old", "workflow", "archive", "old")
    new = OutputOperationIntent("new", "workflow", "archive", "new")
    coordinator.begin(old)
    coordinator.begin(new)
    assert coordinator.settle(OutputOperationResult("old", "workflow", "archive", "succeeded")) is False
    assert coordinator.settle(OutputOperationResult("new", "workflow", "archive", "succeeded")) is True
    assert [(item.operation_id, item.state) for item in presenter.results] == [
        ("old", "pending"),
        ("new", "pending"),
        ("new", "succeeded"),
    ]


def test_cancel_all_projects_cancelled_and_rejects_late_completion() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    copy = OutputOperationIntent("copy-op", "workflow", "copy", "text")
    speech = OutputOperationIntent("speech-op", "global", "speech", "text")
    coordinator.begin(copy)
    coordinator.begin(speech)

    cancelled = coordinator.cancel_all()

    assert cancelled == (copy, speech)
    assert coordinator.settle(OutputOperationResult("copy-op", "workflow", "copy", "succeeded")) is False
    assert [(item.operation_id, item.state) for item in presenter.results] == [
        ("copy-op", "pending"),
        ("speech-op", "pending"),
        ("copy-op", "cancelled"),
        ("speech-op", "cancelled"),
    ]


def test_paste_warning_preserves_dispatch_specific_terminal_state() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("paste-op", "workflow", "paste", "text")
    coordinator.begin(intent)

    assert coordinator.settle(OutputOperationResult(
        "paste-op", "workflow", "paste", "dispatched_unconfirmed",
        message="Confirm the target before trying again.",
    )) is True

    assert presenter.results[-1].state == "dispatched_unconfirmed"
    assert presenter.results[-1].message == "Confirm the target before trying again."


@pytest.mark.parametrize(
    ("outcome", "expected_state"),
    [
        (PasteOutcome("failed", "not_dispatched", "not_required", "Paste failed."), "failed"),
        (PasteOutcome("cancelled", "not_dispatched", "not_required"), "cancelled"),
        (
            PasteOutcome("dispatched_unconfirmed", "dispatched_unconfirmed", "restored", "Paste was sent."),
            "dispatched_unconfirmed",
        ),
        (
            PasteOutcome("cleanup_failed", "dispatched_unconfirmed", "failed", "Clipboard restore failed."),
            "cleanup_failed",
        ),
    ],
)
def test_finish_paste_maps_only_legal_terminal_states(outcome, expected_state) -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("paste-op", "workflow", "paste", "text")
    coordinator.begin(intent)

    assert coordinator.settle(paste_outcome_result(intent, outcome)) is True

    assert presenter.results[-1].state == expected_state


def test_paste_cannot_report_confirmed_success() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("paste-op", "workflow", "paste", "text")
    coordinator.begin(intent)

    with pytest.raises(ValueError, match="unsupported paste"):
        coordinator.settle(OutputOperationResult("paste-op", "workflow", "paste", "succeeded"))


@pytest.mark.parametrize(
    ("kind", "state"),
    [("paste", "succeeded"), ("copy", "dispatched_unconfirmed"), ("archive", "cleanup_failed")],
)
def test_output_operation_result_rejects_incompatible_kind_and_state(kind, state) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        OutputOperationResult("op", "workflow", kind, state)


def test_cancel_all_can_wait_for_running_paste_truth_while_cancelling_other_outputs() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    paste = OutputOperationIntent("paste-op", "workflow", "paste", "text")
    copy = OutputOperationIntent("copy-op", "workflow", "copy", "text")
    coordinator.begin(paste)
    coordinator.begin(copy)

    cancelled = coordinator.cancel_all(exclude_operation_ids=frozenset({"paste-op"}))

    assert cancelled == (copy,)
    assert coordinator.settle(OutputOperationResult(
        "paste-op", "workflow", "paste", "dispatched_unconfirmed", message="Paste was sent."
    )) is True


def test_settle_rejects_pending_and_stale_result_does_not_touch_active_tracker() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("current", "workflow", "copy", "text")
    coordinator.begin(intent)

    with pytest.raises(ValueError, match="belongs to begin"):
        coordinator.settle(OutputOperationResult("current", "workflow", "copy", "pending"))
    assert coordinator.settle(OutputOperationResult("stale", "workflow", "copy", "cancelled")) is False
    assert coordinator.settle(OutputOperationResult("current", "workflow", "copy", "cancelled")) is True


def test_coordinator_owns_lease_through_replacement_and_terminal_settlement() -> None:
    presenter = Presenter()
    user_control = UserControlCoordinator()
    coordinator = OutputOperationCoordinator(presenter)
    coordinator.bind_user_control(user_control)
    coordinator.begin(OutputOperationIntent("old", "workflow", "copy", "old"))
    coordinator.begin(OutputOperationIntent("new", "workflow", "copy", "new"))

    assert [item.operation_id for item in user_control.interrupt_all().operations] == ["new"]


def test_tracker_failure_cannot_orphan_interruption_lease() -> None:
    class Handle:
        def fail(self) -> None:
            raise RuntimeError("tracker failed")

        def succeed(self) -> None:
            raise AssertionError

        def cancel(self) -> None:
            raise AssertionError

    class Tracker:
        def start(self, _operation_id, _kind):
            return Handle()

    presenter = Presenter()
    user_control = UserControlCoordinator()
    coordinator = OutputOperationCoordinator(presenter, Tracker())
    coordinator.bind_user_control(user_control)
    intent = OutputOperationIntent("op", "workflow", "copy", "text")
    coordinator.begin(intent)

    with pytest.raises(RuntimeError, match="tracker failed"):
        coordinator.fail(intent, RuntimeError("copy failed"))

    assert user_control.interrupt_all().operations == ()
    assert presenter.results[-1].state == "failed"
