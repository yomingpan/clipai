from __future__ import annotations

import pytest

from ClipAI.core.models import OutputOperationIntent
from ClipAI.services.output_operation import OutputOperationCoordinator


class Presenter:
    def __init__(self) -> None:
        self.results = []

    def present_output_operation(self, result) -> None:
        self.results.append(result)


def test_operation_projects_pending_then_success() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("op", "workflow", "copy", "text")
    coordinator.run(intent, lambda: None)
    assert [result.state for result in presenter.results] == ["pending", "succeeded"]


def test_failure_is_visible_and_carries_user_facing_error() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    intent = OutputOperationIntent("op", "workflow", "paste", "text")
    with pytest.raises(RuntimeError, match="paste failed"):
        coordinator.run(intent, lambda: (_ for _ in ()).throw(RuntimeError("paste failed")))
    assert presenter.results[-1].state == "failed"
    assert presenter.results[-1].error.message == "paste failed"


def test_late_completion_cannot_replace_newer_same_kind_operation() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    old = OutputOperationIntent("old", "workflow", "archive", "old")
    new = OutputOperationIntent("new", "workflow", "archive", "new")
    coordinator.begin(old)
    coordinator.begin(new)
    assert coordinator.succeed(old) is False
    assert coordinator.succeed(new) is True
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
    assert coordinator.succeed(copy) is False
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

    assert coordinator.warn(
        intent,
        "dispatched_unconfirmed",
        "Confirm the target before trying again.",
    ) is True

    assert presenter.results[-1].state == "dispatched_unconfirmed"
    assert presenter.results[-1].message == "Confirm the target before trying again."


def test_cancel_all_can_wait_for_running_paste_truth_while_cancelling_other_outputs() -> None:
    presenter = Presenter()
    coordinator = OutputOperationCoordinator(presenter)
    paste = OutputOperationIntent("paste-op", "workflow", "paste", "text")
    copy = OutputOperationIntent("copy-op", "workflow", "copy", "text")
    coordinator.begin(paste)
    coordinator.begin(copy)

    cancelled = coordinator.cancel_all(exclude_operation_ids=frozenset({"paste-op"}))

    assert cancelled == (copy,)
    assert coordinator.warn(
        paste,
        "dispatched_unconfirmed",
        "Paste was sent.",
    ) is True
