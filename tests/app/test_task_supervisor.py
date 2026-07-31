from __future__ import annotations

import threading
import time
import pytest

from ClipAI.app.task_supervisor import TaskSupervisor


def test_cancel_many_reports_settled_only_after_running_work_finishes() -> None:
    supervisor = TaskSupervisor(max_workers=1)
    started = threading.Event()
    release = threading.Event()
    settled = threading.Event()

    def work() -> None:
        started.set()
        release.wait(timeout=2)

    supervisor.submit("visible-work", work, lambda _error: None)
    assert started.wait(timeout=1)

    supervisor.cancel_many(("visible-work",), settled.set)

    assert settled.is_set() is False
    release.set()
    assert settled.wait(timeout=1)
    supervisor.shutdown()


def test_cancelled_queued_work_is_not_reported_as_an_unhandled_error() -> None:
    supervisor = TaskSupervisor(max_workers=1)
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def block() -> None:
        started.set()
        release.wait(timeout=2)

    supervisor.submit("blocking", block, errors.append)
    assert started.wait(timeout=1)
    supervisor.submit("queued", lambda: None, errors.append)

    settled = threading.Event()
    supervisor.cancel_many(("queued",), settled.set)

    assert settled.wait(timeout=1)
    assert errors == []
    release.set()
    supervisor.shutdown()


def test_media_and_maintenance_saturation_does_not_block_interactive_work() -> None:
    supervisor = TaskSupervisor(maintenance_workers=1)
    release = threading.Event()
    media_started = threading.Event()
    maintenance_started = threading.Event()
    interactive_started = threading.Event()

    supervisor.submit("media", lambda: (media_started.set(), release.wait(2)), lambda _error: None, task_class="media")
    supervisor.submit("maintenance", lambda: (maintenance_started.set(), release.wait(2)), lambda _error: None, task_class="maintenance")
    assert media_started.wait(1) and maintenance_started.wait(1)

    supervisor.submit("interactive", interactive_started.set, lambda _error: None, task_class="interactive")
    assert interactive_started.wait(0.1)
    release.set()
    supervisor.shutdown()


def test_duplicate_active_identity_is_rejected() -> None:
    supervisor = TaskSupervisor(maintenance_workers=1)
    release = threading.Event()
    supervisor.submit("same", lambda: release.wait(2), lambda _error: None)
    with pytest.raises(RuntimeError, match="already active"):
        supervisor.submit("same", lambda: None, lambda _error: None)
    release.set()
    supervisor.shutdown()


def test_running_cancellation_uses_owned_hook_and_settles_once() -> None:
    supervisor = TaskSupervisor(maintenance_workers=1)
    started = threading.Event()
    cancelled = threading.Event()
    settled = threading.Event()

    def work() -> None:
        started.set()
        cancelled.wait(2)

    supervisor.submit("running", work, lambda _error: None, cancellation_hook=cancelled.set)
    assert started.wait(1)
    supervisor.cancel_many(("running", "running"), lambda: settled.set())
    assert cancelled.is_set()
    assert settled.wait(1)
    supervisor.shutdown()


def test_shutdown_suppresses_late_error_callbacks() -> None:
    supervisor = TaskSupervisor(maintenance_workers=1)
    release = threading.Event()
    errors = []

    def fail_late() -> None:
        release.wait(2)
        raise RuntimeError("late")

    supervisor.submit("late", fail_late, errors.append, cancellation_hook=release.set)
    supervisor.shutdown()
    time.sleep(0.02)
    assert errors == []
