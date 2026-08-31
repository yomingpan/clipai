from __future__ import annotations

import asyncio
import threading

import pytest

from ClipAI.app.provider_execution import ProviderExecutionModule


def test_module_startup_does_not_wait_for_provider_lifecycle() -> None:
    lifecycle_started = threading.Event()
    allow_lifecycle_start = threading.Event()
    work_started = threading.Event()
    completed = threading.Event()

    class Lifecycle:
        async def start(self) -> None:
            lifecycle_started.set()
            while not allow_lifecycle_start.is_set():
                await asyncio.sleep(0.01)

        async def close(self) -> None:
            pass

    module = ProviderExecutionModule(Lifecycle())

    async def work() -> str:
        work_started.set()
        return "ready"

    module.start(
        "provider-1",
        work,
        lambda result: completed.set() if result == "ready" else None,
        lambda _error: None,
        lambda: None,
    )

    assert lifecycle_started.wait(timeout=1)
    assert not work_started.wait(timeout=0.05)
    allow_lifecycle_start.set()
    assert completed.wait(timeout=1)
    module.shutdown()


def test_cancelling_one_operation_does_not_cancel_shared_lifecycle_start() -> None:
    lifecycle_started = threading.Event()
    allow_lifecycle_start = threading.Event()
    first_work_started = threading.Event()
    second_work_started = threading.Event()
    first_cancelled = threading.Event()
    second_cancelled = threading.Event()
    second_completed = threading.Event()

    class Lifecycle:
        async def start(self) -> None:
            lifecycle_started.set()
            while not allow_lifecycle_start.is_set():
                await asyncio.sleep(0.01)

        async def close(self) -> None:
            pass

    module = ProviderExecutionModule(Lifecycle())
    assert lifecycle_started.wait(timeout=1)

    async def first_work() -> None:
        first_work_started.set()

    async def second_work() -> None:
        second_work_started.set()

    module.start(
        "provider-1",
        first_work,
        lambda _result: None,
        lambda _error: None,
        first_cancelled.set,
    )
    module.start(
        "provider-2",
        second_work,
        lambda _result: second_completed.set(),
        lambda _error: None,
        second_cancelled.set,
    )

    assert not first_work_started.wait(timeout=0.05)
    assert not second_work_started.is_set()
    assert module.cancel("provider-1") is True
    assert first_cancelled.wait(timeout=0.25)
    allow_lifecycle_start.set()
    assert second_completed.wait(timeout=1)
    assert second_work_started.is_set()
    assert not second_cancelled.is_set()
    module.shutdown()


def test_provider_lifecycle_start_can_retry_after_failure() -> None:
    first_attempt_finished = threading.Event()
    first_error = threading.Event()
    second_completed = threading.Event()
    attempts = 0

    class Lifecycle:
        async def start(self) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                first_attempt_finished.set()
                raise RuntimeError("transport initialization failed")

        async def close(self) -> None:
            pass

    module = ProviderExecutionModule(Lifecycle())
    assert first_attempt_finished.wait(timeout=1)

    module.start(
        "provider-1",
        lambda: asyncio.sleep(0),
        lambda _result: None,
        lambda error: first_error.set()
        if str(error) == "transport initialization failed"
        else None,
        lambda: None,
    )
    assert first_error.wait(timeout=1)

    module.start(
        "provider-2",
        lambda: asyncio.sleep(0),
        lambda _result: second_completed.set(),
        lambda _error: None,
        lambda: None,
    )

    assert second_completed.wait(timeout=1)
    assert attempts == 2
    module.shutdown()


def test_running_provider_operation_is_cancelled_and_settled() -> None:
    module = ProviderExecutionModule()
    started = threading.Event()
    cancelled = threading.Event()

    async def work():
        started.set()
        await asyncio.Event().wait()

    module.start("provider-1", work, lambda _result: None, lambda _error: None, cancelled.set)
    assert started.wait(timeout=1)

    assert module.cancel("provider-1") is True
    assert cancelled.wait(timeout=0.25)
    module.shutdown()


def test_duplicate_provider_operation_identity_is_rejected() -> None:
    module = ProviderExecutionModule()
    started = threading.Event()

    async def work():
        started.set()
        await asyncio.Event().wait()

    module.start("same", work, lambda _result: None, lambda _error: None, lambda: None)
    assert started.wait(timeout=1)
    with pytest.raises(RuntimeError, match="already active"):
        module.start("same", work, lambda _result: None, lambda _error: None, lambda: None)
    module.cancel("same")
    module.shutdown()


def test_shutdown_suppresses_late_callbacks() -> None:
    module = ProviderExecutionModule()
    started = threading.Event()
    callbacks: list[str] = []

    async def work():
        started.set()
        await asyncio.sleep(10)

    module.start("provider-1", work, lambda _result: callbacks.append("result"), lambda _error: callbacks.append("error"), lambda: callbacks.append("cancel"))
    assert started.wait(timeout=1)

    module.shutdown()

    assert callbacks == []


def test_shutdown_closes_shared_async_lifecycle() -> None:
    class Lifecycle:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.closed = threading.Event()

        async def start(self) -> None:
            self.started.set()

        async def close(self) -> None:
            self.closed.set()

    lifecycle = Lifecycle()
    module = ProviderExecutionModule(lifecycle)
    assert lifecycle.started.wait(1)
    module.shutdown()
    assert lifecycle.closed.is_set()


def test_shutdown_cancels_pending_lifecycle_start_before_close() -> None:
    class Lifecycle:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.cancelled = threading.Event()
            self.closed = threading.Event()

        async def start(self) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()

        async def close(self) -> None:
            self.closed.set()

    lifecycle = Lifecycle()
    module = ProviderExecutionModule(lifecycle)
    assert lifecycle.started.wait(timeout=1)

    module.shutdown()

    assert lifecycle.cancelled.is_set()
    assert lifecycle.closed.is_set()


def test_shutdown_is_bounded_when_async_lifecycle_close_stalls() -> None:
    class Lifecycle:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.close_started = threading.Event()

        async def start(self) -> None:
            self.started.set()

        async def close(self) -> None:
            self.close_started.set()
            await asyncio.Event().wait()

    lifecycle = Lifecycle()
    module = ProviderExecutionModule(lifecycle)
    assert lifecycle.started.wait(1)

    module.shutdown()

    assert lifecycle.close_started.is_set()


def test_shutdown_settles_provider_task_cleanup_before_closing_transport() -> None:
    events: list[str] = []
    started = threading.Event()

    class Lifecycle:
        async def start(self) -> None:
            pass

        async def close(self) -> None:
            events.append("transport-closed")

    async def work() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.05)
            events.append("task-cleaned")

    module = ProviderExecutionModule(Lifecycle())
    module.start("provider-1", work, lambda _result: None, lambda _error: None, lambda: None)
    assert started.wait(1)

    module.shutdown()

    assert events == ["task-cleaned", "transport-closed"]


def test_shutdown_does_not_interrupt_cleanup_after_explicit_cancellation() -> None:
    events: list[str] = []
    started = threading.Event()

    class Lifecycle:
        async def start(self) -> None:
            pass

        async def close(self) -> None:
            events.append("transport-closed")

    async def work() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.05)
            events.append("task-cleaned")

    module = ProviderExecutionModule(Lifecycle())
    module.start("provider-1", work, lambda _result: None, lambda _error: None, lambda: None)
    assert started.wait(1)

    assert module.cancel("provider-1") is True
    module.shutdown()

    assert events == ["task-cleaned", "transport-closed"]


def test_task_cleanup_supports_python_310_task_interface(monkeypatch) -> None:
    class Python310Task:
        def __init__(self) -> None:
            self.cancelled = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

        async def _wait(self) -> None:
            return None

        def __await__(self):
            return self._wait().__await__()

    task = Python310Task()
    monkeypatch.setattr(asyncio, "current_task", lambda: object())
    monkeypatch.setattr(asyncio, "all_tasks", lambda: {task})

    asyncio.run(ProviderExecutionModule._cancel_remaining_tasks())

    assert task.cancelled is True
