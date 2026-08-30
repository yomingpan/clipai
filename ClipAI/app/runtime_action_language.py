from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias
import uuid

from ClipAI.app.language_pack_selection_backend import (
    AppActionLanguageSelectionBackend,
)
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import (
    ActionLanguagePackSelectionCompleted,
    SelectActionLanguagePack,
)
from ClipAI.core.ports import ActionLanguagePackSelectionPresenter
from ClipAI.services.action_language_selection import (
    ActionLanguageSelectionCoordinator,
)


ActionLanguageRuntimeCommand: TypeAlias = (
    SelectActionLanguagePack | ActionLanguagePackSelectionCompleted
)


class ActionLanguageRuntimeModule:
    def __init__(
        self,
        *,
        coordinator: ActionLanguageSelectionCoordinator,
        backend: AppActionLanguageSelectionBackend,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        presenter: ActionLanguagePackSelectionPresenter,
    ) -> None:
        self._coordinator = coordinator
        self._backend = backend
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._presenter = presenter

    def handle(self, command: ActionLanguageRuntimeCommand) -> None:
        if isinstance(command, ActionLanguagePackSelectionCompleted):
            update = self._coordinator.complete(
                command.operation_id,
                command.pack_id,
                command.error,
            )
            if not update.ignored:
                self._presenter.set_action_language_selection(update.state)
            return

        operation_id = command.operation_id or uuid.uuid4().hex
        update = self._coordinator.begin(command.pack_id, operation_id)
        if not update.ignored:
            self._presenter.set_action_language_selection(update.state)
        if update.work is None:
            return
        work = update.work

        def validate_and_save() -> None:
            error = self._backend.validate_and_save(work.pack_id)
            self._enqueue(
                ActionLanguagePackSelectionCompleted(
                    work.operation_id,
                    work.pack_id,
                    error,
                )
            )

        self._supervisor.submit(
            f"action-language:{work.operation_id}",
            validate_and_save,
            lambda _error: self._enqueue(
                ActionLanguagePackSelectionCompleted(
                    work.operation_id,
                    work.pack_id,
                    "selection_save_failed",
                )
            ),
            task_class="maintenance",
        )
