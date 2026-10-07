from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeAlias
import uuid

from ClipAI.app.managed_update_handoff import ManagedUpdateHandoffExecutor
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import CheckForManagedUpdate, ManagedUpdateCheckCompleted, ManagedUpdatePreparationProgress
from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, TransactionId, transaction_id
from ClipAI.core.models import ManagedUpdatePresentation
from ClipAI.core.update_preparation import ManagedUpdatePreparation


ManagedUpdateRuntimeCommand: TypeAlias = CheckForManagedUpdate | ManagedUpdateCheckCompleted | ManagedUpdatePreparationProgress


class ManagedUpdatePresenter(Protocol):
    def set_managed_update(self, state: ManagedUpdatePresentation) -> None: ...


class ManagedUpdateRuntimeModule:
    """Own one explicit About-triggered update operation and its projection."""

    def __init__(
        self,
        *,
        executor: ManagedUpdateHandoffExecutor | None,
        identity: ManagedUpdateClientIdentity | None,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        presenter: ManagedUpdatePresenter,
        transaction_id_factory: Callable[[], TransactionId] | None = None,
    ) -> None:
        if (executor is None) != (identity is None):
            raise ValueError("managed update executor and identity must be supplied together")
        self._executor = executor
        self._identity = identity
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._presenter = presenter
        self._transaction_id_factory = transaction_id_factory or (
            lambda: transaction_id(f"update-{uuid.uuid4().hex}")
        )
        self._active_operation_id: str | None = None
        self._preparation: ManagedUpdatePreparation | None = None
        self._stopped = False
        self._state = _unavailable() if identity is None else _idle()

    @property
    def state(self) -> ManagedUpdatePresentation:
        return self._state

    def project(self) -> None:
        self._presenter.set_managed_update(self._state)

    def handle(self, command: ManagedUpdateRuntimeCommand) -> None:
        if self._stopped:
            return
        if isinstance(command, ManagedUpdatePreparationProgress):
            if command.operation_id == self._active_operation_id:
                # Only forward stages belonging to the current operation may project.
                if command.phase == "downloading" and self._state.phase == "checking":
                    self._set(ManagedUpdatePresentation("downloading", "正在下載更新…", False))
                elif command.phase == "preparing" and self._state.phase == "downloading":
                    self._set(ManagedUpdatePresentation("preparing", "正在驗證並準備更新…", False))
            return
        if isinstance(command, ManagedUpdateCheckCompleted):
            self._complete(command)
            return
        if self._identity is None or self._executor is None or self._active_operation_id is not None:
            return
        operation_id = command.operation_id or uuid.uuid4().hex
        self._active_operation_id = operation_id
        self._set(ManagedUpdatePresentation("checking", "正在檢查更新…", False))
        preparation = ManagedUpdatePreparation(
            report_phase=lambda phase: self._enqueue(ManagedUpdatePreparationProgress(operation_id, phase))
        )
        self._preparation = preparation
        identity = self._identity
        executor = self._executor

        def execute() -> None:
            try:
                readiness = executor.execute(identity, self._transaction_id_factory(), preparation=preparation)
            except ManagedUpdateFailure as exc:
                self._enqueue(ManagedUpdateCheckCompleted(operation_id, "failed", exc.code))
            except BaseException:
                self._enqueue(ManagedUpdateCheckCompleted(
                    operation_id, "failed", FailureCode.INTERNAL_ERROR
                ))
            else:
                outcome = "restarting" if readiness is not None else "up_to_date"
                self._enqueue(ManagedUpdateCheckCompleted(operation_id, outcome))

        try:
            self._supervisor.submit(
                f"managed-update:{operation_id}",
                execute,
                lambda _error: self._enqueue(ManagedUpdateCheckCompleted(
                    operation_id, "failed", FailureCode.INTERNAL_ERROR
                )),
                task_class="maintenance",
                cancellation_hook=preparation.cancellation.cancel,
            )
        except BaseException:
            preparation.cancellation.cancel()
            self._active_operation_id = None
            self._preparation = None
            self._set(_failed(FailureCode.INTERNAL_ERROR))

    def stop(self) -> None:
        self._stopped = True
        if self._preparation is not None:
            self._preparation.cancellation.cancel()
        self._active_operation_id = None
        self._preparation = None

    def _complete(self, command: ManagedUpdateCheckCompleted) -> None:
        if command.operation_id != self._active_operation_id:
            return
        self._active_operation_id = None
        self._preparation = None
        if command.outcome == "up_to_date":
            self._set(ManagedUpdatePresentation("up_to_date", "目前已是最新版本。", True))
        elif command.outcome == "restarting":
            self._set(ManagedUpdatePresentation("restarting", "更新已準備完成，正在重新啟動…", False))
        else:
            self._set(_failed(command.failure_code or FailureCode.INTERNAL_ERROR))

    def _set(self, state: ManagedUpdatePresentation) -> None:
        self._state = state
        self._presenter.set_managed_update(state)


def _idle() -> ManagedUpdatePresentation:
    return ManagedUpdatePresentation("idle", "可檢查 GitHub 上的正式穩定版本。", True)


def _unavailable() -> ManagedUpdatePresentation:
    return ManagedUpdatePresentation("unavailable", "僅 managed 安裝支援自動更新。", False)


def _failed(code: FailureCode) -> ManagedUpdatePresentation:
    return ManagedUpdatePresentation("failed", f"更新失敗（{code.value}），可再試一次。", True, code)
