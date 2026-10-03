from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import logging
import time
import uuid
from typing import Protocol, TypeAlias

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import UseEntryPanelClipboard, EntryPanelInputPreparationProgress
from ClipAI.core.commands import CloseEntryPanel, EntryPanelActionSelected, EntryPanelBack, EntryPanelDigitPressed, EntryPanelInputPreparationCompleted, EntryPanelInputPreparationFailed, EntryPanelOpenMore, EntryPanelSearchChanged, EntryPanelSlotSelected, EntryPanelToggleDensity, OpenUnifiedEntryPanel, RetryEntryPanelInput, SetEntryPanelDensity
from ClipAI.core.errors import CancelledError, InputError
from ClipAI.core.models import (
    ActionAdmissionOrigin,
    ActionStartAdmission,
    ActiveWorkflowContext,
    EntryActionRef,
    EntryInputPreparationId,
    EntryInputSourcePreview,
    EntryPanelSnapshot,
    EntryPanelSource,
    ExternalWindowRef,
    ExternalWindowWaitPolicy,
    ExternalWindowActivationOutcome,
    InputTarget,
    ModifierHoldId,
    PreparedInput,
    PressType,
    ResultRoute,
)
from ClipAI.core.ports import EntryPanelPresenter, ExternalWindowActivator
from ClipAI.core.state import CancellationToken
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.entry_panel import EntryPanelCoordinator
from ClipAI.services.entry_input_preview import build_entry_input_preview
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.input_target_resolver import InputTargetResolver
from ClipAI.services.recent_actions import RecentActionHistory


logger = logging.getLogger("clipai.entry_input")


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
        admission_origin: ActionAdmissionOrigin = "shortcut",
        before_first_projection: Callable[[str], None] | None = None,
    ) -> ActionStartAdmission: ...

    def entry_panel_action_block_reason(self, action: EntryActionRef) -> str: ...


EntryPanelRuntimeCommand: TypeAlias = (
    OpenUnifiedEntryPanel
    | EntryPanelDigitPressed
    | EntryPanelInputPreparationCompleted
    | EntryPanelInputPreparationFailed
    | EntryPanelInputPreparationProgress
    | RetryEntryPanelInput
    | UseEntryPanelClipboard
    | CloseEntryPanel
    | EntryPanelActionSelected
    | EntryPanelSlotSelected
    | EntryPanelOpenMore
    | EntryPanelSearchChanged
    | EntryPanelToggleDensity
    | EntryPanelBack
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
        recent_actions: RecentActionHistory | None = None,
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
        self._recent_actions = recent_actions
        self._input_targets = InputTargetResolver()
        self._source: EntryPanelSource | None = None
        self._task_id: str | None = None
        self._preparation_id: EntryInputPreparationId | None = None
        self._prepared_input: PreparedInput | None = None
        self._workflow_selection = False
        self._hold_id: ModifierHoldId | None = None

    @property
    def active_hold_id(self) -> ModifierHoldId | None:
        return self._hold_id

    def open(self, hold_id: ModifierHoldId | None = None) -> EntryPanelSnapshot:
        current = self._coordinator.snapshot
        if current is not None:
            self._hold_id = hold_id
            self._presenter.present_entry_panel(current)
            return current
        self._hold_id = hold_id
        workflow_id = self._workflows.foreground_workflow_id
        workflow_context: ActiveWorkflowContext | None = None
        if workflow_id is not None:
            self._source = EntryPanelSource("workflow", workflow_id=workflow_id)
            workflow_context = self._workflow_context_reader(workflow_id)
            self._workflow_selection = bool(
                workflow_context is not None
                and workflow_context.selected_text
                and workflow_context.selected_text.strip()
            )
        else:
            external = self._external_source_reader()
            self._source = EntryPanelSource(
                "external" if external is not None else "unavailable",
                external_window=external,
                selection_request=self._input_resolver.begin_selection(external) if external is not None else None,
            )
            self._workflow_selection = False
        panel_id = uuid.uuid4().hex
        preparation_id = EntryInputPreparationId(uuid.uuid4().hex)
        self._preparation_id = preparation_id
        self._prepared_input = None
        snapshot = self._coordinator.open(
            panel_id,
            recent=self._recent_actions.refs if self._recent_actions is not None else (),
            disabled=self._disabled_actions(preparing=True),
            preparing=True,
            source_preview=EntryInputSourcePreview("preparing"),
        )
        self._presenter.present_entry_panel(snapshot)
        source = self._source
        if source is None or source.kind == "unavailable":
            self._enqueue(EntryPanelInputPreparationFailed(
                panel_id,
                preparation_id,
                "The original window is no longer available.",
            ))
        elif source.kind == "workflow":
            target = self._input_targets.resolve(workflow_context)
            if target.document is None:
                self._enqueue(EntryPanelInputPreparationFailed(
                    panel_id,
                    preparation_id,
                    "The original Workflow content is no longer available.",
                ))
            else:
                self._enqueue(EntryPanelInputPreparationCompleted(
                    panel_id,
                    preparation_id,
                    PreparedInput(workflow_document=target.document),
                ))
        else:
            self._schedule_external_preparation(panel_id, preparation_id, source)
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
        elif isinstance(command, EntryPanelInputPreparationCompleted):
            self._complete_preparation(command)
        elif isinstance(command, EntryPanelInputPreparationFailed):
            self._fail_preparation(command)
        elif isinstance(command, EntryPanelInputPreparationProgress):
            current = self._coordinator.snapshot
            if (
                current is not None
                and current.panel_id == command.panel_id
                and command.preparation_id == self._preparation_id
                and current.status == "preparing"
            ):
                self._presenter.present_entry_panel(
                    self._coordinator.show_input_progress(command.phase)
                )
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
                self._presenter.present_entry_panel(self._coordinator.open_more())
            elif isinstance(command, EntryPanelSearchChanged):
                self._presenter.present_entry_panel(
                    self._coordinator.set_search(command.text)
                )
            elif isinstance(command, EntryPanelToggleDensity):
                snapshot = self._coordinator.toggle_density()
                self._presenter.present_entry_panel(snapshot)
                self._enqueue(SetEntryPanelDensity(snapshot.density))
            elif isinstance(command, EntryPanelBack):
                snapshot = self._coordinator.back()
                self._presenter.present_entry_panel(snapshot)
            elif isinstance(command, RetryEntryPanelInput):
                self._retry_preparation()
            elif isinstance(command, UseEntryPanelClipboard):
                prepared = self._prepared_input
                if prepared is not None and self._preparation_id is not None and (
                    prepared.clipboard_text_document is not None or prepared.clipboard_image is not None
                ):
                    self._complete_preparation(EntryPanelInputPreparationCompleted(
                        command.panel_id, self._preparation_id,
                        prepared.use_clipboard(),
                    ))

    def close(self, panel_id: str) -> None:
        current = self._coordinator.snapshot
        if current is None or current.panel_id != panel_id:
            return
        self._cancel_preparation()
        self._coordinator.close()
        self._source = None
        self._prepared_input = None
        self._preparation_id = None
        self._hold_id = None
        self._presenter.present_entry_panel(None)

    def select_action(self, action: EntryActionRef) -> None:
        current = self._coordinator.snapshot
        if current is None:
            return
        if current.status == "preparing" or self._prepared_input is None:
            return
        reason = self._workflows.entry_panel_action_block_reason(action)
        if reason:
            self._presenter.present_entry_panel(self._coordinator.show_error(reason))
            return
        try:
            resolved = self._actions.resolve(action.action_id, action.press_type)
        except ValueError as error:
            self._presenter.present_entry_panel(
                self._coordinator.show_error(str(error))
            )
            return
        resolution = self._prepared_input.resolve(resolved.input_mode)
        if resolution.document is None:
            self._presenter.present_entry_panel(
                self._coordinator.show_error(
                    self._input_unavailable_message(resolution.unavailable_reason)
                )
            )
            return
        document = resolution.document
        target_kind = (
            "workflow_result"
            if document.source == "workflow_result"
            else "external_text"
        )

        def register_handoff(workflow_id: str) -> None:
            self._presenter.transition_entry_panel_to_popup(
                current.panel_id,
                workflow_id,
            )

        admission = self._workflows.start_action(
            action.action_id,
            action.press_type,
            input_target=InputTarget(target_kind, document),
            admission_origin="entry_panel",
            before_first_projection=register_handoff,
        )
        if admission.accepted:
            if admission.workflow_id is None:
                self._presenter.present_entry_panel(
                    self._coordinator.show_error(
                        "The admitted Workflow could not be identified."
                    )
                )
                return
            logger.info(
                "Entry input trace stage=action_admitted panel_id=%s workflow_id=%s "
                "action_id=%s press_type=%s",
                current.panel_id,
                admission.workflow_id,
                action.action_id,
                action.press_type,
            )
            self._coordinator.close()
            self._source = None
            self._prepared_input = None
            self._preparation_id = None
            self._hold_id = None
            return
        message = admission.message or "This Action cannot start right now."
        self._presenter.present_entry_panel(self._coordinator.show_error(message))

    def _complete_preparation(
        self,
        command: EntryPanelInputPreparationCompleted,
    ) -> None:
        current = self._coordinator.snapshot
        if (
            current is None
            or current.panel_id != command.panel_id
            or command.preparation_id != self._preparation_id
        ):
            return
        self._task_id = None
        prepared = command.prepared_input
        if (
            prepared.selection_outcome is not None
            and prepared.selection_outcome.status == "unknown"
            and (
                prepared.clipboard_text_document is not None
                or prepared.clipboard_image is not None
            )
        ):
            prepared = prepared.use_clipboard()
        self._prepared_input = prepared
        self._coordinator.complete_input_preparation(
            build_entry_input_preview(
                prepared,
                workflow_selection=self._workflow_selection,
            )
        )
        snapshot = self._coordinator.set_disabled(
            self._disabled_actions(prepared=prepared)
        )
        assert snapshot is not None
        self._presenter.present_entry_panel(snapshot)

    def _fail_preparation(self, command: EntryPanelInputPreparationFailed) -> None:
        current = self._coordinator.snapshot
        if (
            current is None
            or current.panel_id != command.panel_id
            or command.preparation_id != self._preparation_id
        ):
            return
        self._task_id = None
        self._prepared_input = None
        self._coordinator.show_error(
            command.message,
            source_preview=EntryInputSourcePreview("failed", command.message),
        )
        snapshot = self._coordinator.set_disabled(
            self._disabled_actions(failure=command.message)
        )
        assert snapshot is not None
        self._presenter.present_entry_panel(snapshot)

    def _retry_preparation(self) -> None:
        current = self._coordinator.snapshot
        source = self._source
        if (
            current is None
            or current.status == "preparing"
            or source is None
            or source.kind != "external"
        ):
            return
        self._cancel_preparation()
        preparation_id = EntryInputPreparationId(uuid.uuid4().hex)
        self._preparation_id = preparation_id
        self._prepared_input = None
        self._coordinator.begin_input_preparation()
        snapshot = self._coordinator.set_disabled(
            self._disabled_actions(preparing=True)
        )
        assert snapshot is not None
        self._presenter.present_entry_panel(snapshot)
        self._schedule_external_preparation(
            current.panel_id,
            preparation_id,
            source,
        )

    def stop(self) -> None:
        current = self._coordinator.snapshot
        if current is not None:
            self.close(current.panel_id)

    def request_escape(self) -> bool:
        current = self._coordinator.snapshot
        if current is None:
            return False
        self.close(current.panel_id)
        return True

    def refresh_availability(self) -> None:
        current = self._coordinator.snapshot
        snapshot = self._coordinator.set_disabled(
            self._disabled_actions(
                prepared=self._prepared_input,
                preparing=current is not None and current.status == "preparing",
                failure=(
                    current.message
                    if current is not None
                    and current.status == "error"
                    and self._prepared_input is None
                    else ""
                ),
            )
        )
        if snapshot is not None:
            self._presenter.present_entry_panel(snapshot)

    def _schedule_external_preparation(
        self,
        panel_id: str,
        preparation_id: EntryInputPreparationId,
        source: EntryPanelSource,
    ) -> None:
        target = source.external_window
        assert target is not None
        cancellation = CancellationToken()
        task_id = f"entry-panel-input:{preparation_id}"
        self._task_id = task_id
        logger.info(
            "Entry input trace stage=scheduled panel_id=%s preparation_id=%s "
            "target_window=%s target_process_id=%s",
            panel_id,
            preparation_id,
            target.window_token,
            target.process_id,
        )

        def work() -> None:
            notice_sent = False

            def on_waiting() -> None:
                nonlocal notice_sent
                if not notice_sent and not cancellation.is_cancelled:
                    notice_sent = True
                    self._enqueue(EntryPanelInputPreparationProgress(panel_id, preparation_id, "waiting_for_window"))

            try:
                wait_policy = ExternalWindowWaitPolicy()
                activation_started_at = time.monotonic()
                activation = self._external_window_activator.activate(
                    target,
                    cancellation,
                    wait_policy=wait_policy,
                    on_waiting=on_waiting,
                )
                activation_elapsed = time.monotonic() - activation_started_at
                log = logger.info if activation.activated else logger.warning
                log(
                    "Entry input trace stage=activation panel_id=%s "
                    "preparation_id=%s target_window=%s target_process_id=%s "
                    "state=%s elapsed_ms=%s",
                    panel_id,
                    preparation_id,
                    target.window_token,
                    target.process_id,
                    activation.state,
                    round(activation_elapsed * 1000),
                )
                if not activation.activated:
                    self._enqueue(EntryPanelInputPreparationFailed(
                        panel_id,
                        preparation_id,
                        self._window_failure_message(activation),
                    ))
                    return
                request = source.selection_request
                if notice_sent:
                    self._enqueue(EntryPanelInputPreparationProgress(panel_id, preparation_id, "reading"))
                    notice_sent = False
                if request is not None:
                    request = replace(request, operation_id=f"selection:{preparation_id}")
                capture_started_at = time.monotonic()
                prepared = self._input_resolver.prepare_input(cancellation, target=target, request=request)
                logger.info(
                    "Entry input trace stage=capture panel_id=%s preparation_id=%s "
                    "target_window=%s selection_available=%s "
                    "clipboard_text_available=%s clipboard_image_available=%s elapsed_ms=%s",
                    panel_id,
                    preparation_id,
                    target.window_token,
                    prepared.selection_document is not None,
                    prepared.clipboard_text_document is not None,
                    prepared.clipboard_image is not None,
                    round((time.monotonic() - capture_started_at) * 1000),
                )
                confirmation_started_at = time.monotonic()
                confirmation = self._external_window_activator.confirm(
                    target,
                    cancellation,
                    wait_policy=ExternalWindowWaitPolicy(
                        timeout_sec=max(0.0, wait_policy.timeout_sec - activation_elapsed),
                        notice_after_sec=max(0.0, wait_policy.notice_after_sec - activation_elapsed),
                    ),
                    on_waiting=on_waiting,
                )
                log = logger.info if confirmation.activated else logger.warning
                log(
                    "Entry input trace stage=confirmation panel_id=%s "
                    "preparation_id=%s target_window=%s target_process_id=%s "
                    "state=%s elapsed_ms=%s",
                    panel_id,
                    preparation_id,
                    target.window_token,
                    target.process_id,
                    confirmation.state,
                    round((time.monotonic() - confirmation_started_at) * 1000),
                )
                if confirmation.activated:
                    self._enqueue(EntryPanelInputPreparationCompleted(
                        panel_id,
                        preparation_id,
                        prepared,
                    ))
                    return
                self._enqueue(EntryPanelInputPreparationFailed(
                    panel_id,
                    preparation_id,
                    self._window_failure_message(confirmation),
                ))
            except CancelledError:
                logger.info(
                    "Entry input trace stage=cancelled panel_id=%s "
                    "preparation_id=%s target_window=%s",
                    panel_id,
                    preparation_id,
                    target.window_token,
                )
                return
            except (InputError, ValueError) as error:
                logger.warning(
                    "Entry input trace stage=capture_error panel_id=%s "
                    "preparation_id=%s target_window=%s error_type=%s",
                    panel_id,
                    preparation_id,
                    target.window_token,
                    type(error).__name__,
                )
                self._enqueue(EntryPanelInputPreparationFailed(
                    panel_id,
                    preparation_id,
                    str(error),
                ))
            except Exception as error:
                logger.warning(
                    "Entry input trace stage=unexpected_error panel_id=%s "
                    "preparation_id=%s target_window=%s error_type=%s",
                    panel_id,
                    preparation_id,
                    target.window_token,
                    type(error).__name__,
                )
                self._enqueue(EntryPanelInputPreparationFailed(
                    panel_id,
                    preparation_id,
                    "Input preparation failed.",
                ))

        try:
            self._supervisor.submit(
                task_id,
                work,
                lambda _error: None,
                task_class="interactive",
                cancellation_hook=cancellation.cancel,
            )
        except Exception as error:
            self._task_id = None
            logger.warning(
                "Entry input trace stage=scheduling_error panel_id=%s "
                "preparation_id=%s target_window=%s error_type=%s",
                panel_id,
                preparation_id,
                target.window_token,
                type(error).__name__,
            )
            self._enqueue(EntryPanelInputPreparationFailed(
                panel_id,
                preparation_id,
                "Input preparation could not start.",
            ))

    @staticmethod
    def _window_failure_message(outcome: ExternalWindowActivationOutcome) -> str:
        if outcome.state in {"target_focus_timeout", "target_refused_focus"}:
            return "等待原視窗就緒逾時，請重試。"
        if outcome.state in {"target_gone", "target_changed"}:
            return "原視窗已無法使用，請回到來源視窗重新開啟面板。"
        return outcome.message or "無法確認原視窗，請重試。"

    def _cancel_preparation(self) -> None:
        if self._task_id is not None:
            self._supervisor.cancel(self._task_id)
            self._task_id = None

    def _matches_panel(self, panel_id: str) -> bool:
        current = self._coordinator.snapshot
        return current is not None and current.panel_id == panel_id

    def _disabled_actions(
        self,
        *,
        prepared: PreparedInput | None = None,
        preparing: bool = False,
        failure: str = "",
    ) -> dict[EntryActionRef, str]:
        disabled: dict[EntryActionRef, str] = {}
        actions = list(self._coordinator.actions)
        if self._recent_actions is not None:
            actions.extend(
                action
                for action in self._recent_actions.refs
                if action not in actions
                and action.press_type in {"short", "long"}
                and self._actions.contains(action.action_id)
            )
        for action in actions:
            reason = self._workflows.entry_panel_action_block_reason(action)
            if not reason and failure:
                reason = failure
            if not reason and prepared is not None:
                try:
                    resolved = self._actions.resolve(
                        action.action_id,
                        action.press_type,
                    )
                    resolution = prepared.resolve(resolved.input_mode)
                    if resolution.document is None:
                        reason = self._input_unavailable_message(
                            resolution.unavailable_reason
                        )
                except ValueError as error:
                    reason = str(error)
            if reason:
                disabled[action] = reason
        return disabled

    @staticmethod
    def _input_unavailable_message(reason: str | None) -> str:
        if reason == "selection_unknown":
            return "無法確認反白內容，請重試或選擇使用剪貼簿。"
        if reason == "clipboard_image_unavailable":
            return "此功能需要剪貼簿截圖。"
        return "找不到可用的選取內容或剪貼簿內容。"
