from __future__ import annotations

import asyncio
import threading

import pytest

from ClipAI.app.provider_execution import ProviderExecutionModule


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
