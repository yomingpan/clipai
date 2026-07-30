from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
import threading


class TaskSupervisor:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="clipai-worker")
        self._tasks: dict[str, Future[None]] = {}
        self._lock = threading.RLock()
        self._closed = False

    def submit(
        self,
        session_id: str,
        work: Callable[[], None],
        on_unhandled_error: Callable[[BaseException], None],
    ) -> Future[None]:
        with self._lock:
            if self._closed:
                raise RuntimeError("task supervisor is closed")
            future = self._executor.submit(work)
            self._tasks[session_id] = future

        def finish(done: Future[None]) -> None:
            with self._lock:
                if self._tasks.get(session_id) is done:
                    self._tasks.pop(session_id, None)
            if done.cancelled():
                return
            try:
                error = done.exception()
            except BaseException as exc:
                error = exc
            if error is not None:
                on_unhandled_error(error)

        future.add_done_callback(finish)
        return future

    def cancel(self, session_id: str) -> None:
        with self._lock:
            future = self._tasks.get(session_id)
        if future is not None:
            future.cancel()

    def cancel_many(self, session_ids: Iterable[str], on_settled: Callable[[], None]) -> None:
        with self._lock:
            futures = {
                future
                for session_id in dict.fromkeys(session_ids)
                if (future := self._tasks.get(session_id)) is not None
            }
        if not futures:
            on_settled()
            return

        remaining = len(futures)
        settlement_lock = threading.Lock()

        def settled(_future: Future[None]) -> None:
            nonlocal remaining
            with settlement_lock:
                remaining -= 1
                complete = remaining == 0
            if complete:
                on_settled()

        for future in futures:
            future.add_done_callback(settled)
        for future in futures:
            future.cancel()

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            futures = list(self._tasks.values())
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

