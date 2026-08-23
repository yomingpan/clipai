from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
import logging
import threading
from typing import Any, Protocol, TypeVar


T = TypeVar("T")
logger = logging.getLogger(__name__)


class AsyncLifecycle(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...


class ProviderExecutionModule:
    """Own provider-network tasks and the AsyncClient that executes them."""

    def __init__(self, lifecycle: AsyncLifecycle | None = None) -> None:
        self._loop = asyncio.new_event_loop()
        self._lifecycle = lifecycle
        self._tasks: dict[str, Future[Any]] = {}
        self._loop_tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancellation_requested: set[asyncio.Task[Any]] = set()
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(target=self._run_loop, name="clipai-provider", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2):
            raise RuntimeError("provider execution loop did not start")

    def start(
        self,
        operation_id: str,
        work: Callable[[], Awaitable[T]],
        on_result: Callable[[T], None],
        on_error: Callable[[BaseException], None],
        on_cancelled: Callable[[], None],
    ) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("provider execution module is closed")
            if operation_id in self._tasks:
                raise RuntimeError(f"provider operation is already active: {operation_id}")

            async def run() -> None:
                task = asyncio.current_task()
                if task is not None:
                    with self._lock:
                        self._loop_tasks[operation_id] = task
                try:
                    try:
                        result = await work()
                    except asyncio.CancelledError:
                        if not self._is_closed():
                            on_cancelled()
                        raise
                    except BaseException as error:
                        if not self._is_closed():
                            on_error(error)
                    else:
                        if not self._is_closed():
                            on_result(result)
                finally:
                    if task is not None:
                        with self._lock:
                            if self._loop_tasks.get(operation_id) is task:
                                self._loop_tasks.pop(operation_id, None)
                            self._cancellation_requested.discard(task)

            future = asyncio.run_coroutine_threadsafe(run(), self._loop)
            self._tasks[operation_id] = future
            future.add_done_callback(lambda done: self._settle(operation_id, done))

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            future = self._tasks.get(operation_id)
            task = self._loop_tasks.get(operation_id)
            if future is None:
                return False
            if task is not None:
                self._cancellation_requested.add(task)
            cancelled = bool(future.cancel())
            if not cancelled and task is not None:
                self._cancellation_requested.discard(task)
            return cancelled

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            already_cancelling = frozenset(self._cancellation_requested)
        self._settle_provider_tasks(already_cancelling)
        close = asyncio.run_coroutine_threadsafe(self._close_lifecycle(), self._loop)
        try:
            close.result(timeout=1)
        except TimeoutError:
            logger.warning("[clipai] Provider transport shutdown exceeded 1 second; cancelling close.")
            close.cancel()
            self._drain_loop_cancellation()
        except Exception as error:
            logger.warning("[clipai] Provider transport shutdown failed: %s", type(error).__name__)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=1)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        if self._lifecycle is not None:
            self._loop.run_until_complete(self._lifecycle.start())
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()

    async def _close_lifecycle(self) -> None:
        if self._lifecycle is not None:
            await self._lifecycle.close()

    def _settle_provider_tasks(self, already_cancelling: frozenset[asyncio.Task[Any]]) -> None:
        settlement = asyncio.run_coroutine_threadsafe(
            self._cancel_remaining_tasks(already_cancelling), self._loop
        )
        try:
            settlement.result(timeout=1)
        except TimeoutError:
            logger.warning("[clipai] Provider task cleanup exceeded 1 second; continuing shutdown.")
            settlement.cancel()
            self._drain_loop_cancellation()
        except Exception as error:
            logger.warning("[clipai] Provider task cleanup failed: %s", type(error).__name__)

    @staticmethod
    async def _cancel_remaining_tasks(
        already_cancelling: frozenset[asyncio.Task[Any]] = frozenset(),
    ) -> None:
        current = asyncio.current_task()
        pending = tuple(
            task
            for task in asyncio.all_tasks()
            if task is not current and not task.done()
        )
        for task in pending:
            if task not in already_cancelling:
                task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _drain_loop_cancellation(self) -> None:
        barrier = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), self._loop)
        try:
            barrier.result(timeout=0.25)
        except Exception:
            pass

    def _settle(self, operation_id: str, future: Future[Any]) -> None:
        with self._lock:
            if self._tasks.get(operation_id) is future:
                self._tasks.pop(operation_id, None)

    def _is_closed(self) -> bool:
        with self._lock:
            return self._closed
