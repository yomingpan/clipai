from __future__ import annotations

from collections.abc import Callable
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

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            futures = list(self._tasks.values())
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

