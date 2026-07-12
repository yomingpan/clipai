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
