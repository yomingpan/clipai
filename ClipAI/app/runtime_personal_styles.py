from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import (
    ClosePersonalStyles,
    ImportPersonalStyle,
    OpenPersonalStyles,
    PersonalStyleOperationCompleted,
    SelectPersonalStyle,
)
from ClipAI.core.ports import OperationTracker, PersonalStylePresenter
from ClipAI.services.personal_styles import PersonalStyleCoordinator, PersonalStyleUpdate


PersonalStyleRuntimeCommand: TypeAlias = (
    OpenPersonalStyles
    | ClosePersonalStyles
    | ImportPersonalStyle
    | SelectPersonalStyle
    | PersonalStyleOperationCompleted
)


class PersonalStyleRuntimeModule:
    """Schedules profile persistence and projects its authoritative lifecycle."""

    def __init__(
        self,
        *,
        coordinator: PersonalStyleCoordinator,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        presenter: PersonalStylePresenter | None = None,
        operation_tracker: OperationTracker | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._presenter = presenter
        self._operation_tracker = operation_tracker
        self._open = False

    def handle(self, command: PersonalStyleRuntimeCommand) -> None:
        if isinstance(command, OpenPersonalStyles):
            self._open = True
            if self._presenter is not None:
                self._presenter.show_personal_styles(self._coordinator.state)
        elif isinstance(command, ClosePersonalStyles):
            self._open = False
            if self._presenter is not None:
                self._presenter.close_personal_styles()
        elif isinstance(command, ImportPersonalStyle):
            self._start(
                self._coordinator.begin_import(
                    command.path,
                    command.operation_id or uuid.uuid4().hex,
                )
            )
        elif isinstance(command, SelectPersonalStyle):
            self._start(
                self._coordinator.begin_select(
                    command.profile_id,
                    command.operation_id or uuid.uuid4().hex,
                )
            )
        elif isinstance(command, PersonalStyleOperationCompleted):
            self._project(self._coordinator.complete(command.operation_id, command.error))

    def _start(self, update: PersonalStyleUpdate) -> None:
        self._project(update)
        if update.work is None:
            return
        coordinator, work = self._coordinator, update.work

        def persist() -> None:
            self._enqueue(
                PersonalStyleOperationCompleted(
                    work.operation_id,
                    coordinator.execute(work),
                )
            )

        try:
            self._supervisor.submit(
                f"personal-style:{work.operation_id}",
                persist,
                lambda _error: self._enqueue(
                    PersonalStyleOperationCompleted(
                        work.operation_id,
                        "Unable to save the personal style. The previous selection remains active.",
                    )
                ),
                task_class="interactive",
            )
        except BaseException:
            self._project(self._coordinator.complete(
                work.operation_id,
                "Unable to start the personal style update. The previous selection remains active.",
            ))

    def _project(self, update: PersonalStyleUpdate) -> None:
        if update.ignored:
            return
        if self._presenter is not None:
            if self._open:
                self._presenter.set_personal_styles(update.state)
        if update.state.operation_state == "failed" and self._operation_tracker is not None:
            self._operation_tracker.report_error(update.state.message)
