from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import asyncio
import threading
from typing import Any, Literal, TypeVar


TaskClass = Literal["interactive", "media", "maintenance"]
T = TypeVar("T")


@dataclass
class _TaskRecord:
    future: Future[Any]
    cancellation_hook: Callable[[], None] | None
    cancellation_requested: bool = False


class TaskSupervisor:
    """Own non-provider blocking work with isolated capacity lanes."""

    def __init__(self, maintenance_workers: int = 1, *, max_workers: int | None = None) -> None:
        if max_workers is not None:
            maintenance_workers = max_workers
        if maintenance_workers < 1:
            raise ValueError("maintenance_workers must be at least 1")
        self._executors: dict[TaskClass, ThreadPoolExecutor] = {
            "interactive": ThreadPoolExecutor(max_workers=2, thread_name_prefix="clipai-interactive"),
            "media": ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipai-media"),
            "maintenance": ThreadPoolExecutor(max_workers=maintenance_workers, thread_name_prefix="clipai-maintenance"),
        }
        self._tasks: dict[str, _TaskRecord] = {}
        self._lock = threading.RLock()
        self._closed = False

    def submit(
        self,
        task_id: str,
        work: Callable[[], T],
        on_unhandled_error: Callable[[BaseException], None],
        *,
        task_class: TaskClass = "interactive",
        cancellation_hook: Callable[[], None] | None = None,
    ) -> Future[T]:
        with self._lock:
            if self._closed:
                raise RuntimeError("task supervisor is closed")
            if task_id in self._tasks:
                raise RuntimeError(f"task identity is already active: {task_id}")
            future = self._executors[task_class].submit(work)
            self._tasks[task_id] = _TaskRecord(future, cancellation_hook)

        def finish(done: Future[T]) -> None:
            with self._lock:
                record = self._tasks.get(task_id)
                if record is None or record.future is not done:
                    return
                self._tasks.pop(task_id, None)
                closed = self._closed
            if closed or done.cancelled():
                return
            try:
                error = done.exception()
            except BaseException as exc:
                error = exc
            if error is not None:
                on_unhandled_error(error)

        future.add_done_callback(finish)
        return future

    async def run(
        self,
        task_id: str,
        work: Callable[[], T],
        *,
        task_class: TaskClass = "interactive",
        cancellation_hook: Callable[[], None] | None = None,
    ) -> T:
        future = self.submit(
            task_id,
            work,
            lambda _error: None,
            task_class=task_class,
            cancellation_hook=cancellation_hook,
        )
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            self.cancel(task_id)
            raise

    def cancel(self, task_id: str) -> None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            if record.future.cancel():
                return
            hook = self._request_running_cancellation(record)
        if hook is not None:
            hook()

    def cancel_many(self, task_ids: Iterable[str], on_settled: Callable[[], None]) -> None:
        with self._lock:
            records = {
                id(record.future): record
                for task_id in dict.fromkeys(task_ids)
                if (record := self._tasks.get(task_id)) is not None
            }
        if not records:
            on_settled()
            return

        remaining = len(records)
        settlement_lock = threading.Lock()

        def settled(_future: Future[Any]) -> None:
            nonlocal remaining
            with settlement_lock:
                remaining -= 1
                complete = remaining == 0
            if complete:
                on_settled()

        hooks: list[Callable[[], None]] = []
        for record in records.values():
            record.future.add_done_callback(settled)
            if not record.future.cancel():
                with self._lock:
                    hook = self._request_running_cancellation(record)
                if hook is not None:
                    hooks.append(hook)
        for hook in hooks:
            hook()

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            records = tuple(self._tasks.values())
            hooks = tuple(
                hook
                for record in records
                if not record.future.cancel()
                if (hook := self._request_running_cancellation(record)) is not None
            )
        for hook in hooks:
            hook()
        wait((record.future for record in records), timeout=0.25)
        for executor in self._executors.values():
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _request_running_cancellation(record: _TaskRecord) -> Callable[[], None] | None:
        if record.cancellation_requested:
            return None
        record.cancellation_requested = True
        return record.cancellation_hook
