from __future__ import annotations

import threading
from typing import Protocol

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.models import EntryActionRef
from ClipAI.support.diagnostics import IncidentReporter


class RecentActionStore(Protocol):
    def save(self, refs: tuple[EntryActionRef, ...]) -> None: ...


class RecentActionPersistence:
    """Coalesce atomic recent writes without delaying Action completion."""

    def __init__(
        self,
        store: RecentActionStore,
        supervisor: TaskSupervisor,
        incident_reporter: IncidentReporter | None = None,
    ) -> None:
        self._store = store
        self._supervisor = supervisor
        self._incident_reporter = incident_reporter
        self._lock = threading.Lock()
        self._pending: tuple[EntryActionRef, ...] | None = None
        self._running = False

    def schedule(self, refs: tuple[EntryActionRef, ...]) -> None:
        with self._lock:
            self._pending = refs
            if self._running:
                return
            self._running = True
        try:
            self._supervisor.submit(
                "recent-actions:persist",
                self._persist_latest,
                self._report_failure,
                task_class="maintenance",
            )
        except Exception as error:
            with self._lock:
                self._running = False
            self._report_failure(error)

    def _persist_latest(self) -> None:
        while True:
            with self._lock:
                refs = self._pending
                self._pending = None
                if refs is None:
                    self._running = False
                    return
            try:
                self._store.save(refs)
            except Exception as error:
                self._report_failure(error)

    def _report_failure(self, error: BaseException) -> None:
        if self._incident_reporter is not None:
            self._incident_reporter.report(error, context="recent-actions:persist")
