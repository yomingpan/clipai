from __future__ import annotations

from collections.abc import Callable
import uuid
from typing import Protocol, TypeAlias

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import CloseEntryPanel, EntryPanelActionSelected, EntryPanelDigitPressed, EntryPanelEscape, EntryPanelInputPrepared, EntryPanelOpenMore, EntryPanelSearchChanged, EntryPanelSlotSelected, EntryPanelToggleDensity, OpenUnifiedEntryPanel
from ClipAI.core.errors import CancelledError, InputError
from ClipAI.core.models import (
    ActionStartAdmission,
    ActiveWorkflowContext,
    EntryActionRef,
    EntryPanelSelectionId,
    EntryPanelSnapshot,
    EntryPanelSource,
    ExternalWindowRef,
    InputTarget,
    ModifierHoldId,
    PressType,
    ResultRoute,
)
from ClipAI.core.ports import EntryPanelPresenter, ExternalWindowActivator
from ClipAI.core.state import CancellationToken
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.entry_panel import EntryPanelCoordinator
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.input_target_resolver import InputTargetResolver


class WorkflowActionAdmitter(Protocol):
    @property
    def foreground_workflow_id(self) -> str | None: ...

    def start_action(
        self,
        action_id: str,
        press_type: PressType,
        *,
        result_route: ResultRoute = "popup",
        input_target: InputTarget | None = None,
    ) -> ActionStartAdmission: ...


EntryPanelRuntimeCommand: TypeAlias = (
    OpenUnifiedEntryPanel
    | EntryPanelDigitPressed
    | EntryPanelInputPrepared
    | CloseEntryPanel
    | EntryPanelActionSelected
    | EntryPanelSlotSelected
    | EntryPanelOpenMore
    | EntryPanelSearchChanged
    | EntryPanelToggleDensity
    | EntryPanelEscape
)


class EntryPanelRuntimeModule:
    """Owns one Panel lifecycle and its identity-scoped input preparation."""

    def __init__(
        self,
        *,
        coordinator: EntryPanelCoordinator,
        actions: ActionCatalog,
        workflows: WorkflowActionAdmitter,
        workflow_context_reader: Callable[[str], ActiveWorkflowContext | None],
        external_source_reader: Callable[[], ExternalWindowRef | None],
        external_window_activator: ExternalWindowActivator,
        input_resolver: InputResolver,
        supervisor: TaskSupervisor,
        enqueue: Callable[[object], None],
        presenter: EntryPanelPresenter,
    ) -> None:
        self._coordinator = coordinator
        self._actions = actions
        self._workflows = workflows
        self._workflow_context_reader = workflow_context_reader
        self._external_source_reader = external_source_reader
        self._external_window_activator = external_window_activator
        self._input_resolver = input_resolver
        self._supervisor = supervisor
        self._enqueue = enqueue
        self._presenter = presenter
        self._input_targets = InputTargetResolver()
        self._source: EntryPanelSource | None = None
        self._task_id: str | None = None
        self._hold_id: ModifierHoldId | None = None

    def open(self, hold_id: ModifierHoldId | None = None) -> EntryPanelSnapshot:
        current = self._coordinator.snapshot
        if current is not None:
            self._hold_id = hold_id
            self._presenter.present_entry_panel(current)
            return current
        self._hold_id = hold_id
        workflow_id = self._workflows.foreground_workflow_id
        if workflow_id is not None:
            self._source = EntryPanelSource("workflow", workflow_id=workflow_id)
        else:
            external = self._external_source_reader()
            self._source = EntryPanelSource(
                "external" if external is not None else "unavailable",
                external_window=external,
            )
        snapshot = self._coordinator.open(uuid.uuid4().hex)
        self._presenter.present_entry_panel(snapshot)
        return snapshot

    def handle(self, command: EntryPanelRuntimeCommand) -> None:
        if isinstance(command, OpenUnifiedEntryPanel):
            self.open(command.hold_id)
        elif isinstance(command, EntryPanelDigitPressed):
            if self._hold_id is not None and command.hold_id == self._hold_id:
                decision = self._coordinator.select_digit(command.digit)
                self._presenter.present_entry_panel(decision.snapshot)
                if decision.action is not None:
                    self.select_action(decision.action)
        elif isinstance(command, EntryPanelInputPrepared):
            self._complete_preparation(command)
        elif self._matches_panel(command.panel_id):
            if isinstance(command, CloseEntryPanel):
                self.close(command.panel_id)
            elif isinstance(command, EntryPanelActionSelected):
                self.select_action(command.action)
            elif isinstance(command, EntryPanelSlotSelected):
                decision = self._coordinator.select_digit(str(command.slot))
                self._presenter.present_entry_panel(decision.snapshot)
                if decision.action is not None:
                    self.select_action(decision.action)
            elif isinstance(command, EntryPanelOpenMore):
                self._cancel_preparation()
                self._presenter.present_entry_panel(self._coordinator.open_more())
            elif isinstance(command, EntryPanelSearchChanged):
                self._presenter.present_entry_panel(
                    self._coordinator.set_search(command.text)
                )
            elif isinstance(command, EntryPanelToggleDensity):
                self._presenter.present_entry_panel(
                    self._coordinator.toggle_density()
                )
            elif isinstance(command, EntryPanelEscape):
                self._cancel_preparation()
                snapshot = self._coordinator.escape()
                if snapshot is None:
                    self._source = None
                    self._hold_id = None
                self._presenter.present_entry_panel(snapshot)

    def close(self, panel_id: str) -> None:
        current = self._coordinator.snapshot
        if current is None or current.panel_id != panel_id:
            return
        self._cancel_preparation()
        self._coordinator.close()
        self._source = None
        self._hold_id = None
        self._presenter.present_entry_panel(None)

    def select_action(self, action: EntryActionRef) -> None:
        current = self._coordinator.snapshot
        if current is None:
            return
        self._cancel_preparation()
        selection_id = EntryPanelSelectionId(uuid.uuid4().hex)
        self._presenter.present_entry_panel(
            self._coordinator.begin_preparation(selection_id)
        )
        source = self._source
        if source is None or source.kind == "unavailable":
            self._enqueue(EntryPanelInputPrepared(
                current.panel_id,
                selection_id,
                action,
                error="The original window is no longer available.",
            ))
            return
        if source.kind == "workflow":
            context = self._workflow_context_reader(source.workflow_id)
            target = self._input_targets.resolve(context)
            if context is None or target.document is None:
                self._enqueue(EntryPanelInputPrepared(
                    current.panel_id,
                    selection_id,
                    action,
                    error="The original Workflow content is no longer available.",
                ))
            else:
                self._enqueue(EntryPanelInputPrepared(
                    current.panel_id,
                    selection_id,
                    action,
                    document=target.document,
                ))
            return
        self._schedule_external_preparation(current.panel_id, selection_id, action, source)

    def _complete_preparation(self, command: EntryPanelInputPrepared) -> None:
        current = self._coordinator.snapshot
        if current is None or current.panel_id != command.panel_id:
            return
        settled = self._coordinator.settle_preparation(command.selection_id)
        if settled is None:
            return
        self._task_id = None
        if command.error or command.document is None:
            message = command.error or "Input preparation failed."
            self._presenter.present_entry_panel(self._coordinator.show_error(message))
            return
        target_kind = (
            "workflow_result"
            if command.document.source == "workflow_result"
            else "external_text"
        )
        admission = self._workflows.start_action(
            command.action.action_id,
            command.action.press_type,
            input_target=InputTarget(target_kind, command.document),
        )
        if admission.accepted:
            self.close(command.panel_id)
            return
        message = admission.message or "This Action cannot start right now."
        self._presenter.present_entry_panel(self._coordinator.show_error(message))

    def stop(self) -> None:
        current = self._coordinator.snapshot
        if current is not None:
            self.close(current.panel_id)

    def _schedule_external_preparation(
        self,
        panel_id: str,
        selection_id: EntryPanelSelectionId,
        action: EntryActionRef,
        source: EntryPanelSource,
    ) -> None:
        target = source.external_window
        assert target is not None
        cancellation = CancellationToken()
        task_id = f"entry-panel-input:{selection_id}"
        self._task_id = task_id

        def work() -> None:
            try:
                activation = self._external_window_activator.activate(target, cancellation)
                if not activation.activated:
                    self._enqueue(EntryPanelInputPrepared(
                        panel_id,
                        selection_id,
                        action,
                        error=activation.message or "The original window could not be activated.",
                    ))
                    return
                resolved = self._actions.resolve(action.action_id, action.press_type)
                document = self._input_resolver.resolve(resolved.input_mode, cancellation)
                self._enqueue(EntryPanelInputPrepared(
                    panel_id,
                    selection_id,
                    action,
                    document=document,
                ))
            except CancelledError:
                return
            except (InputError, ValueError) as error:
                self._enqueue(EntryPanelInputPrepared(
                    panel_id,
                    selection_id,
                    action,
                    error=str(error),
                ))
            except Exception:
                self._enqueue(EntryPanelInputPrepared(
                    panel_id,
                    selection_id,
                    action,
                    error="Input preparation failed.",
                ))

        self._supervisor.submit(
            task_id,
            work,
            lambda _error: None,
            task_class="interactive",
            cancellation_hook=cancellation.cancel,
        )

    def _cancel_preparation(self) -> None:
        if self._task_id is not None:
            self._supervisor.cancel(self._task_id)
            self._task_id = None

    def _matches_panel(self, panel_id: str) -> bool:
        current = self._coordinator.snapshot
        return current is not None and current.panel_id == panel_id
