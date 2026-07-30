from __future__ import annotations

import threading

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
