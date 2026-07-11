from __future__ import annotations

import pytest

from ClipAI.services.operation_lifecycle import OperationLifecycleCoordinator


class Indicator:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def set_status(self, status: str) -> None:
        self.statuses.append(status)

    def set_memory_active(self, active: bool) -> None:
        del active


class ScheduledCall:
    def __init__(self, delay: float, callback) -> None:
        self.delay = delay
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.callback()


class Scheduler:
    def __init__(self) -> None:
        self.calls: list[ScheduledCall] = []

    def __call__(self, delay: float, callback) -> ScheduledCall:
        call = ScheduledCall(delay, callback)
        self.calls.append(call)
        return call


def make_coordinator(*, ready: bool = True):
    indicator = Indicator()
    scheduler = Scheduler()
    coordinator = OperationLifecycleCoordinator(indicator, ready=ready, schedule=scheduler)
    return coordinator, indicator, scheduler


def test_readiness_sets_and_updates_idle_baseline() -> None:
    coordinator, indicator, _ = make_coordinator(ready=False)
    assert indicator.statuses == ["warning"]
    coordinator.set_ready(True)
    assert indicator.statuses[-1] == "idle"


def test_success_resets_to_ready_baseline_after_two_seconds() -> None:
    coordinator, indicator, scheduler = make_coordinator()
    operation = coordinator.start("llm:1", "llm")
    operation.succeed()
    assert indicator.statuses == ["idle", "processing", "success"]
    assert scheduler.calls[-1].delay == 2.0
    scheduler.calls[-1].fire()
    assert indicator.statuses[-1] == "idle"


def test_overlapping_success_keeps_processing_until_last_operation() -> None:
    coordinator, indicator, scheduler = make_coordinator()
    llm = coordinator.start("llm:1", "llm")
    tts = coordinator.start("tts:1", "tts")
    llm.succeed()
    assert indicator.statuses[-1] == "processing"
    assert scheduler.calls == []
    tts.succeed()
    assert indicator.statuses[-1] == "success"


def test_error_temporarily_wins_then_projects_remaining_operation() -> None:
    coordinator, indicator, scheduler = make_coordinator()
    llm = coordinator.start("llm:1", "llm")
    coordinator.start("tts:1", "tts")
    llm.fail()
    assert indicator.statuses[-1] == "error"
    assert scheduler.calls[-1].delay == 3.0
    scheduler.calls[-1].fire()
    assert indicator.statuses[-1] == "processing"


def test_error_remains_visible_when_an_operation_starts_or_finishes() -> None:
    coordinator, indicator, scheduler = make_coordinator()
    failed = coordinator.start("llm:1", "llm")
    failed.fail()
    reset = scheduler.calls[-1]
    tts = coordinator.start("tts:1", "tts")
    tts.succeed()
    assert indicator.statuses[-1] == "error"
    assert reset.cancelled is False
    reset.fire()
    assert indicator.statuses[-1] == "idle"


def test_cancel_does_not_flash_success_and_uses_warning_baseline() -> None:
    coordinator, indicator, scheduler = make_coordinator(ready=False)
    operation = coordinator.start("llm:1", "llm")
    operation.cancel()
    assert indicator.statuses[-1] == "warning"
    assert scheduler.calls == []


def test_handle_terminal_methods_are_idempotent() -> None:
    coordinator, indicator, scheduler = make_coordinator()
    operation = coordinator.start("llm:1", "llm")
    operation.succeed()
    operation.fail()
    operation.cancel()
    assert indicator.statuses == ["idle", "processing", "success"]
    assert len(scheduler.calls) == 1


def test_start_during_transient_status_cancels_reset_and_processes() -> None:
    coordinator, indicator, scheduler = make_coordinator()
    first = coordinator.start("llm:1", "llm")
    first.succeed()
    reset = scheduler.calls[-1]
    coordinator.start("tts:1", "tts")
    assert reset.cancelled is True
    assert indicator.statuses[-1] == "processing"
    reset.fire()
    assert indicator.statuses[-1] == "processing"


def test_duplicate_and_invalid_operations_are_rejected() -> None:
    coordinator, _, _ = make_coordinator()
    coordinator.start("llm:1", "llm")
    with pytest.raises(ValueError, match="already active"):
        coordinator.start("llm:1", "llm")
    with pytest.raises(ValueError, match="must not be empty"):
        coordinator.start(" ", "tts")
    with pytest.raises(ValueError, match="Unsupported"):
        coordinator.start("other:1", "other")  # type: ignore[arg-type]


def test_stop_cancels_timer_and_late_handle_has_no_effect() -> None:
    coordinator, indicator, scheduler = make_coordinator(ready=False)
    finished = coordinator.start("llm:1", "llm")
    finished.fail()
    reset = scheduler.calls[-1]
    active = coordinator.start("tts:1", "tts")
    coordinator.stop()
    assert reset.cancelled is True
    assert indicator.statuses[-1] == "warning"
    active.succeed()
    reset.fire()
    assert indicator.statuses[-1] == "warning"
