from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal, TypeAlias
import uuid

from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import ActivateWorkflow, AppCommand, CancelSession, CloseSession, ContextualSourceCaptured, ContextualSourceCaptureFailed, FollowUp, NavigateWorkflowBack, OpenContextualQuestion, PasteOperationCompleted, ShortcutPressInvoked, StartAction, SubmitContextualQuestion, TogglePin, WorkflowAttentionCompleted, WorkflowStepAccepted
from ClipAI.core.errors import InputError, PersonalStyleUnavailableError
from ClipAI.core.models import ActionAdmissionOrigin, ActionInvocation, ActionStartAdmission, ControlSurfaceRef, EntryActionRef, InputDocument, InputTarget, InterruptibleOperationRef, PasteTarget, PersonalStyleProfile, PressType, ResultRoute, WorkflowAttention
from ClipAI.core.ports import ApplicationView, OperationTracker, UserNotifier, VoiceCaptureContextReader, WorkflowAttentionPresenter, WorkflowContextReader
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceCaptureSurfaceContext, VoiceDraftTarget, VoiceFollowUpTarget, VoiceOrigin
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.follow_up_continuation import CONTEXTUAL_QUESTION_ACTION_ID, FollowUpContinuation, VOICE_DRAFT_FOLLOW_UP_ACTION_ID
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.input_target_resolver import InputTargetResolver
from ClipAI.services.personal_styles import PersonalStyleCoordinator
from ClipAI.services.provider_configuration import ProviderConfigurationCoordinator
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.recent_actions import RecentActionHistory
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_intent import ShortcutIntentCoordinator
from ClipAI.services.shortcut_sequence import ShortcutSequenceCoordinator
from ClipAI.services.speech_coordinator import SpeechCoordinator
from ClipAI.services.workflow_controller import WorkflowController
from ClipAI.services.user_control import InterruptibleOperationLease, UserControlCoordinator
from ClipAI.support.diagnostics import IncidentReporter


WorkflowPresentation: TypeAlias = Literal["visible", "headless"]


@dataclass(frozen=True)
class WorkflowInvocationFailed:
    workflow_id: str
    error: BaseException


@dataclass(frozen=True)
class HeadlessWorkflowFinished:
    workflow_id: str


@dataclass(frozen=True)
class WorkflowSnapshotReady:
    snapshot: SessionSnapshot
    presentation: WorkflowPresentation


WorkflowRuntimeCommand: TypeAlias = (
    StartAction
    | OpenContextualQuestion
    | SubmitContextualQuestion
    | ContextualSourceCaptured
    | ContextualSourceCaptureFailed
    | CloseSession
    | CancelSession
    | TogglePin
    | FollowUp
    | ActivateWorkflow
    | NavigateWorkflowBack
    | WorkflowInvocationFailed
    | HeadlessWorkflowFinished
    | WorkflowSnapshotReady
    | WorkflowAttentionCompleted
    | WorkflowStepAccepted
)


@dataclass(frozen=True)
class _WorkflowRecord:
    controller: WorkflowController
    binding: ProviderExecutionBinding
    presentation: WorkflowPresentation
    personal_style: PersonalStyleProfile | None = None


@dataclass(frozen=True)
class VoiceCaptureIntent:
    """One explicit request for runtime-owned Voice destination admission."""

    trigger: Literal["shortcut", "popup"]
    workflow_id: str | None = None
    focused_surface: ControlSurfaceRef | None = None
    active_voice_workflow_id: str | None = None


@dataclass(frozen=True)
class VoiceCaptureAdmission:
    """The sole runtime decision about where a Voice capture may operate."""

    kind: Literal["create", "voice_review", "follow_up", "continue", "rejected"]
    workflow_id: str | None = None
    target: VoiceDraftTarget | VoiceFollowUpTarget | None = None
    message: str = ""


class _RuntimeWorkflowPresenter:
    def __init__(self, enqueue: Callable[[object], None], presentation: WorkflowPresentation) -> None:
        self._enqueue = enqueue
        self._presentation = presentation

    def render(self, snapshot: SessionSnapshot) -> None:
        self._enqueue(WorkflowSnapshotReady(snapshot, self._presentation))


class WorkflowRuntimeModule:
    """Owns desktop coordination for workflow commands and workflow identities."""

    def __init__(
        self,
        *,
        actions: ActionCatalog,
        shortcuts: ShortcutCatalog,
        execute_action: ActionExecutor,
        view: ApplicationView,
        provider_execution: ProviderExecutionModule,
        enqueue: Callable[[object], None],
        provider_configuration: ProviderConfigurationCoordinator,
        workflow_context_reader: WorkflowContextReader,
        voice_capture_context_reader: VoiceCaptureContextReader | None = None,
        incident_reporter: IncidentReporter,
        operation_tracker: OperationTracker | None = None,
        notifier: UserNotifier | None = None,
        speech_coordinator: SpeechCoordinator | None = None,
        input_targets: InputTargetResolver | None = None,
        shortcut_intents: ShortcutIntentCoordinator | None = None,
        user_control: UserControlCoordinator | None = None,
        attention_presenter: WorkflowAttentionPresenter | None = None,
        personal_styles: PersonalStyleCoordinator | None = None,
        input_resolver: InputResolver | None = None,
        supervisor: TaskSupervisor | None = None,
        recent_actions: RecentActionHistory | None = None,
        recent_action_sink: Callable[[tuple[EntryActionRef, ...]], None] | None = None,
    ) -> None:
        self._actions = actions
        self._execute_action = execute_action
        self._view = view
        self._provider_execution = provider_execution
        self._enqueue = enqueue
        self._provider_configuration = provider_configuration
        self._workflow_context_reader = workflow_context_reader
        self._voice_capture_context_reader = voice_capture_context_reader
        self._incident_reporter = incident_reporter
        self._operation_tracker = operation_tracker
        self._notifier = notifier
        self._speech_coordinator = speech_coordinator
        self._input_targets = input_targets or InputTargetResolver()
        self._records: dict[str, _WorkflowRecord] = {}
        self._user_control = user_control
        self._attention_presenter = attention_presenter
        self._personal_styles = personal_styles
        self._input_resolver = input_resolver
        self._supervisor = supervisor
        self._recent_actions = recent_actions
        self._recent_action_sink = recent_action_sink
        self._pending_attention: dict[str, tuple[str, str]] = {}
        self._interruption_leases: dict[str, InterruptibleOperationLease] = {}
        self._foreground_id: str | None = None
        self._shortcut_intents = shortcut_intents or ShortcutSequenceCoordinator(
            shortcuts,
            on_waiting=self._sequence_waiting,
            on_error=self._sequence_error,
            on_cancel_active=self._cancel_headless_workflows,
        )

    def controller_for(self, workflow_id: str) -> WorkflowController | None:
        record = self._records.get(workflow_id)
        return record.controller if record is not None else None

    def _new_controller(
        self,
        initial: SessionSnapshot,
        presentation: WorkflowPresentation,
    ) -> WorkflowController:
        return WorkflowController(
            initial,
            _RuntimeWorkflowPresenter(self._enqueue, presentation),
            on_step_accepted=lambda workflow_id, step_id: self._enqueue(
                WorkflowStepAccepted(workflow_id, step_id)
            ),
        )

    def create_voice_workflow(self, workflow_id: str, target: PasteTarget | None) -> WorkflowController:
        """Create the visible Workflow that exclusively owns one Voice draft."""
        if workflow_id in self._records:
            raise RuntimeError(f"workflow identity is already registered: {workflow_id}")
        if not self._replace_unpinned_visible_workflow():
            raise RuntimeError("cannot create a Voice Workflow while a pinned Workflow owns the popup")
        controller = self._new_controller(
            SessionSnapshot(
                workflow_id,
                0,
                SessionStatus.VOICE_PREPARING,
                "voice_input",
                "Voice Input",
                self._provider_configuration.active_binding.model,
                content="",
                source_preview="Voice Input draft",
                status_text="Preparing microphone…",
                available_actions=(),
                result_completeness="none",
                voice_origin=VoiceOrigin(target),
            ),
            "visible",
        )
        self._register(workflow_id, controller, self._provider_configuration.active_binding, "visible")
        self._foreground_id = workflow_id
        return controller

    def admit_voice_capture(self, intent: VoiceCaptureIntent) -> VoiceCaptureAdmission:
        """Choose one semantic destination without leaking the policy to either trigger."""
        if intent.trigger == "popup":
            workflow_id = intent.workflow_id
            if workflow_id is None:
                return VoiceCaptureAdmission("rejected")
            record = self._records.get(workflow_id)
            if record is None or record.presentation != "visible":
                return VoiceCaptureAdmission("rejected", workflow_id=workflow_id)
            return self._voice_capture_admission_for_visible(intent, workflow_id, record)
        visible = self._visible_record()
        if visible is not None:
            workflow_id, record = visible
            return self._voice_capture_admission_for_visible(intent, workflow_id, record)
        if intent.focused_surface is not None:
            if intent.focused_surface.kind != "workflow":
                return VoiceCaptureAdmission(
                    "rejected",
                    message="Close the active ClipAI window, then try again.",
                )
            target = self._voice_review_target(intent.focused_surface.surface_id)
            if target is not None:
                return VoiceCaptureAdmission(
                    "voice_review",
                    workflow_id=intent.focused_surface.surface_id,
                    target=target,
                )
        return VoiceCaptureAdmission("create")

    def _voice_capture_admission_for_visible(
        self,
        intent: VoiceCaptureIntent,
        workflow_id: str,
        record: _WorkflowRecord,
    ) -> VoiceCaptureAdmission:
        shortcut = intent.trigger == "shortcut"
        if shortcut and intent.active_voice_workflow_id == workflow_id:
            self._request_attention(
                workflow_id,
                "語音輸入進行中",
                duration_ms=1500,
                warning=False,
            )
            return VoiceCaptureAdmission("continue", workflow_id=workflow_id)
        focused_surface = intent.focused_surface
        if shortcut and focused_surface is None:
            return VoiceCaptureAdmission(
                "rejected",
                workflow_id=workflow_id,
                message="請先點選目前的 ClipAI 視窗再使用語音輸入，或關閉視窗後開始新的語音輸入。",
            )
        if shortcut:
            assert focused_surface is not None
            if focused_surface.kind != "workflow" or focused_surface.surface_id != workflow_id:
                return VoiceCaptureAdmission(
                    "rejected",
                    workflow_id=workflow_id,
                    message="請先點選目前的 ClipAI 視窗再使用語音輸入。",
                )

        snapshot = record.controller.snapshot
        provider_active = snapshot.active_invocation_id is not None or snapshot.status in {
            SessionStatus.READING_INPUT,
            SessionStatus.PREPARING_REQUEST,
            SessionStatus.REQUESTING_PROVIDER,
            SessionStatus.PROCESSING_RESULT,
        }
        if provider_active:
            return VoiceCaptureAdmission(
                "rejected",
                workflow_id=workflow_id,
                message="AI 正在回答，完成後再追問。" if shortcut else "",
            )
        context = self._voice_capture_surface_context(workflow_id)
        if shortcut and context is not None and context.follow_up_requested:
            return VoiceCaptureAdmission(
                "follow_up",
                workflow_id=workflow_id,
                target=VoiceFollowUpTarget(workflow_id),
            )
        if snapshot.status is SessionStatus.VOICE_REVIEW:
            target = self._voice_review_target(workflow_id, context)
            if target is not None:
                return VoiceCaptureAdmission("voice_review", workflow_id=workflow_id, target=target)
            return VoiceCaptureAdmission("rejected", workflow_id=workflow_id)
        if (
            snapshot.status in {SessionStatus.CONTEXT_QUESTION, SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED}
            and (snapshot.status is SessionStatus.CONTEXT_QUESTION or snapshot.displayed_step_index >= 0)
            and "follow_up" in snapshot.available_actions
        ):
            return VoiceCaptureAdmission(
                "follow_up",
                workflow_id=workflow_id,
                target=VoiceFollowUpTarget(workflow_id),
            )
        return VoiceCaptureAdmission(
            "rejected",
            workflow_id=workflow_id,
            message="這份內容目前無法使用 Follow-up。" if shortcut else "",
        )

    def _voice_review_target(
        self,
        workflow_id: str,
        context: VoiceCaptureSurfaceContext | None = None,
    ) -> VoiceDraftTarget | None:
        record = self._records.get(workflow_id)
        if record is None or record.presentation != "visible":
            return None
        context = context or self._voice_capture_surface_context(workflow_id)
        selection = context.selection if context is not None else None
        if selection is None:
            return None
        return record.controller.freeze_voice_insertion(*selection)

    def _voice_capture_surface_context(self, workflow_id: str) -> VoiceCaptureSurfaceContext | None:
        reader = self._voice_capture_context_reader
        if reader is None:
            return None
        context = reader.voice_capture_surface_context(workflow_id)
        return context if context is not None and context.workflow_id == workflow_id else None

    def bind_user_control(self, user_control: UserControlCoordinator) -> None:
        self._user_control = user_control

    def has_foreground_workflow(self) -> bool:
        return self._foreground_id in self._records

    @property
    def foreground_workflow_id(self) -> str | None:
        return self._foreground_id if self._foreground_id in self._records else None

    def entry_panel_action_block_reason(self, action: EntryActionRef) -> str:
        try:
            resolved = self._actions.resolve(action.action_id, action.press_type)
        except ValueError as error:
            return str(error)
        return self._entry_panel_block_reason(resolved)

    def _entry_panel_block_reason(self, action) -> str:
        provider_active = any(
            record.controller.snapshot.active_invocation_id is not None
            and record.controller.snapshot.status in {
                SessionStatus.PREPARING_REQUEST,
                SessionStatus.REQUESTING_PROVIDER,
                SessionStatus.PROCESSING_RESULT,
            }
            for record in self._records.values()
        )
        if provider_active:
            return "AI 正在回答，完成後再選擇功能。"
        if self._personal_styles is not None:
            try:
                self._personal_styles.bind(action)
            except (PersonalStyleUnavailableError, ValueError) as error:
                return str(error)
        return ""

    def observe_paste_completion(
        self,
        command: PasteOperationCompleted,
    ) -> Literal["ignored", "released", "closed"]:
        """Apply semantic Foreground Workflow policy from authoritative Paste truth."""
        record = self._records.get(command.workflow_id)
        if (
            command.outcome.state != "dispatched_unconfirmed"
            or self._foreground_id != command.workflow_id
            or record is None
            or record.presentation != "visible"
            or record.controller.snapshot.pinned
        ):
            return "ignored"
        self._foreground_id = None
        return "closed" if record.controller.snapshot.voice_origin is not None else "released"

    def resolve_shortcut(self, command: ShortcutPressInvoked) -> AppCommand | None:
        return self._shortcut_intents.resolve(command)

    def reject_shortcut_attempt(self) -> None:
        self._shortcut_intents.reject_attempt()

    def cancel_shortcut_sequence(self) -> None:
        self._shortcut_intents.cancel()

    def has_pending_shortcut_sequence(self) -> bool:
        return self._shortcut_intents.is_waiting

    def cancel_active_operations(self) -> tuple[str, ...]:
        self._shortcut_intents.cancel()
        task_ids: list[str] = []
        for workflow_id, record in tuple(self._records.items()):
            capture_id = record.controller.stop_contextual_source_capture()
            if capture_id is not None and self._supervisor is not None:
                self._supervisor.cancel(f"context-source:{capture_id}")
            active_id = record.controller.snapshot.active_invocation_id
            if record.presentation == "headless":
                if active_id is not None:
                    task_ids.append(active_id)
                self._end(
                    workflow_id,
                    "cancel",
                    cancel_task=False,
                )
                if self._speech_coordinator is not None:
                    self._speech_coordinator.cancel_workflow(workflow_id)
                continue
            stopped_id = record.controller.stop_active()
            if stopped_id is not None:
                task_ids.append(stopped_id)
        return tuple(task_ids)

    def cancel_operation(self, operation_id: str) -> tuple[str, ...]:
        for workflow_id, record in tuple(self._records.items()):
            if record.controller.snapshot.active_invocation_id != operation_id:
                continue
            if record.presentation == "headless":
                self._end(workflow_id, "cancel", cancel_task=False)
                if self._speech_coordinator is not None:
                    self._speech_coordinator.cancel_workflow(workflow_id)
            else:
                record.controller.stop_active()
            self._provider_execution.cancel(operation_id)
            return (operation_id,)
        return ()

    def cancel_all_content_operations(self) -> tuple[str, ...]:
        return self.cancel_active_operations()

    def handle(self, command: WorkflowRuntimeCommand) -> None:
        if isinstance(command, StartAction):
            self.start_action(
                command.action_id,
                command.press_type,
                result_route=command.result_route,
            )
        elif isinstance(command, OpenContextualQuestion):
            self._open_contextual_question()
        elif isinstance(command, SubmitContextualQuestion):
            self._submit_contextual_question(command)
        elif isinstance(command, ContextualSourceCaptured):
            self._complete_contextual_source(command)
        elif isinstance(command, ContextualSourceCaptureFailed):
            self._fail_contextual_source(command)
        elif isinstance(command, CloseSession):
            self._close(command.session_id)
        elif isinstance(command, CancelSession):
            self._cancel(command.session_id)
        elif isinstance(command, TogglePin):
            controller = self.controller_for(command.session_id)
            if controller and controller.snapshot.status not in {SessionStatus.CANCELLED, SessionStatus.CLOSED}:
                controller.toggle_pin()
        elif isinstance(command, FollowUp):
            self._follow_up(command)
        elif isinstance(command, ActivateWorkflow):
            record = self._records.get(command.workflow_id)
            if record is not None and record.presentation == "visible":
                self._foreground_id = command.workflow_id
        elif isinstance(command, NavigateWorkflowBack):
            controller = self.controller_for(command.workflow_id)
            if controller is not None:
                controller.navigate_back()
        elif isinstance(command, WorkflowInvocationFailed):
            self._handle_unhandled(command.workflow_id, command.error)
        elif isinstance(command, HeadlessWorkflowFinished):
            self._finish_headless(command.workflow_id)
        elif isinstance(command, WorkflowSnapshotReady):
            self._project_snapshot(command.snapshot, command.presentation)
        elif isinstance(command, WorkflowAttentionCompleted):
            self._complete_attention(command)
        elif isinstance(command, WorkflowStepAccepted):
            self._record_accepted_step(command)

    def stop(self) -> None:
        self._shortcut_intents.cancel()
        self._cancel_headless_workflows()
        for workflow_id in tuple(self._records):
            self._end(workflow_id, "cancel")

    def show_last_error(self) -> None:
        error = self._operation_tracker.last_error if self._operation_tracker is not None else None
        if error is not None and self._notifier is not None:
            self._notifier.notify("ClipAI — Last Error", " ".join(part for part in (error.message, error.suggestion) if part))

    def start_action(
        self,
        action_id: str,
        press_type: PressType,
        *,
        result_route: ResultRoute = "popup",
        input_target: InputTarget | None = None,
        admission_origin: ActionAdmissionOrigin = "shortcut",
    ) -> ActionStartAdmission:
        """Admit one Action through the existing Workflow runtime."""
        try:
            action = self._actions.resolve(action_id, press_type)
        except ValueError as error:
            return ActionStartAdmission("rejected", "unknown_action", str(error))
        if admission_origin == "entry_panel":
            reason = self._entry_panel_block_reason(action)
            if reason:
                return ActionStartAdmission("blocked", "entry_panel_unavailable", reason)
        if self._personal_styles is not None:
            try:
                action = self._personal_styles.bind(action)
            except PersonalStyleUnavailableError as error:
                self._sequence_error(str(error), "Open Personal Styles from the tray menu.")
                return ActionStartAdmission(
                    "rejected",
                    "personal_style_unavailable",
                    str(error),
                )
        command = StartAction(action_id, press_type, result_route)
        if result_route == "speech":
            self._start_headless_action(action, command, input_target=input_target)
            return ActionStartAdmission("accepted")
        target = input_target or self._input_targets.resolve(
            self._foreground_context(),
            action.external_fallback,
        )
        document = target.document
        contextual = target.kind == "workflow_result" and document is not None
        if contextual:
            assert document is not None
            workflow_id = document.workflow_id
            parent_step_id = document.step_id
            if not workflow_id or not parent_step_id:
                return ActionStartAdmission(
                    "rejected",
                    "workflow_source_invalid",
                    "The original Workflow content is no longer available.",
                )
            record = self._records.get(workflow_id)
            if record is None or record.presentation != "visible":
                return ActionStartAdmission(
                    "rejected",
                    "workflow_source_unavailable",
                    "The original Workflow content is no longer available.",
                )
            controller = record.controller
            valid_voice_origin = (
                parent_step_id == "voice-origin"
                and controller.snapshot.status is SessionStatus.VOICE_REVIEW
            )
            if not valid_voice_origin and parent_step_id not in {
                step.step_id for step in controller.snapshot.steps
            }:
                return ActionStartAdmission(
                    "rejected",
                    "workflow_source_unavailable",
                    "The original Workflow content is no longer available.",
                )
        else:
            visible = self._visible_record()
            if visible is not None and visible[1].controller.snapshot.pinned:
                workflow_id, record = visible
                controller = record.controller
                parent_step_id = None
            else:
                if not self._replace_unpinned_visible_workflow():
                    return ActionStartAdmission(
                        "blocked",
                        "pinned_workflow",
                        "Close or unpin the current Workflow, then try again.",
                    )
                workflow_id = uuid.uuid4().hex
                parent_step_id = None
                controller = self._new_controller(
                    SessionSnapshot(workflow_id, 0, SessionStatus.CREATED, action.id, action.name, self._provider_configuration.active_binding.model),
                    "visible",
                )
                record = self._register(
                    workflow_id,
                    controller,
                    self._provider_configuration.active_binding,
                    "visible",
                    personal_style=action.personal_style,
                )
        if action.personal_style_mode is not None and self._personal_styles is not None:
            if record.personal_style is not None:
                if (
                    action.personal_style is None
                    or action.personal_style.profile_id != record.personal_style.profile_id
                ):
                    action = self._personal_styles.bind_to(
                        self._actions.resolve(command.action_id, command.press_type),
                        record.personal_style,
                    )
            elif action.personal_style is not None:
                record = replace(record, personal_style=action.personal_style)
                self._records[workflow_id] = record
        active_id = controller.snapshot.active_invocation_id
        if active_id is not None:
            controller.cancel_active()
            self._provider_execution.cancel(active_id)
        if controller.snapshot.pinned and self._speech_coordinator is not None:
            self._speech_coordinator.cancel_workflow(workflow_id)
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            command.press_type,
            target,
            workflow_id=workflow_id,
            parent_step_id=parent_step_id,
        )
        controller.begin_invocation(invocation, action)
        self._foreground_id = workflow_id
        self._submit_invocation(
            workflow_id,
            invocation.invocation_id,
            lambda: self._execute_action.execute_invocation(action, invocation, controller, binding=record.binding),
        )
        return ActionStartAdmission("accepted")

    def _start_headless_action(
        self,
        action,
        command: StartAction,
        *,
        input_target: InputTarget | None = None,
    ) -> None:
        context = self._foreground_context()
        target = input_target or self._input_targets.resolve(context, action.external_fallback)
        workflow_id = uuid.uuid4().hex
        controller = self._new_controller(
            SessionSnapshot(workflow_id, 0, SessionStatus.CREATED, action.id, action.name, self._provider_configuration.active_binding.model),
            "headless",
        )
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            command.press_type,
            target,
            result_route="speech",
            workflow_id=workflow_id,
        )
        controller.begin_invocation(invocation, action)
        record = self._register(
            workflow_id,
            controller,
            self._provider_configuration.active_binding,
            "headless",
            personal_style=action.personal_style,
        )

        async def execute() -> None:
            await self._execute_action.execute_invocation(action, invocation, controller, binding=record.binding)
            if controller.snapshot.status in {SessionStatus.COMPLETED, SessionStatus.FAILED}:
                self._enqueue(HeadlessWorkflowFinished(workflow_id))

        self._submit_invocation(workflow_id, invocation.invocation_id, execute)

    def _cancel_headless_workflows(self) -> None:
        workflow_ids = tuple(
            workflow_id
            for workflow_id, record in self._records.items()
            if record.presentation == "headless"
        )
        for workflow_id in workflow_ids:
            self._end(workflow_id, "cancel")
            if self._speech_coordinator is not None:
                self._speech_coordinator.cancel_workflow(workflow_id)

    def _follow_up(self, command: FollowUp) -> None:
        record = self._records.get(command.session_id)
        if record is None or record.presentation != "visible" or not command.text.strip():
            return
        controller = record.controller
        previous = controller.snapshot
        if (
            previous.displayed_step_index >= 0
            and previous.steps[previous.displayed_step_index].action_id == CONTEXTUAL_QUESTION_ACTION_ID
            and previous.contextual_source_text
            and previous.contextual_source_kind in {"selection", "clipboard"}
        ):
            continuation = FollowUpContinuation.for_contextual_question(
                command.text.strip(),
                previous.contextual_source_text,
                previous.contextual_source_kind,
                history=previous.steps[: previous.displayed_step_index + 1],
            )
            self._start_follow_up_continuation(record, continuation)
            return
        if previous.voice_origin is not None and (
            previous.displayed_step_index < 0
            or previous.steps[previous.displayed_step_index].action_id == VOICE_DRAFT_FOLLOW_UP_ACTION_ID
        ):
            continuation = FollowUpContinuation.for_voice_draft(
                command.text.strip(),
                previous.voice_origin.text,
                history=previous.steps[: previous.displayed_step_index + 1],
            )
            self._start_follow_up_continuation(record, continuation)
            return
        if previous.displayed_step_index < 0:
            return
        parent = previous.steps[previous.displayed_step_index]
        action = self._actions.resolve(parent.action_id, parent.press_type)
        if self._personal_styles is not None:
            try:
                action = (
                    self._personal_styles.bind_to(action, record.personal_style)
                    if record.personal_style is not None
                    else self._personal_styles.bind(action)
                )
            except PersonalStyleUnavailableError as error:
                self._sequence_error(str(error), "Open Personal Styles from the tray menu.")
                return
        continuation = FollowUpContinuation.for_action(
            action,
            command.text.strip(),
            history=previous.steps[: previous.displayed_step_index + 1],
        )
        self._start_follow_up_continuation(record, continuation)

    def _start_follow_up_continuation(
        self,
        record: _WorkflowRecord,
        continuation: FollowUpContinuation,
    ) -> None:
        action = continuation.action
        workflow_id = record.controller.snapshot.session_id
        invocation = ActionInvocation(
            uuid.uuid4().hex,
            action.id,
            action.press_type,
            InputTarget(
                "workflow_result",
                continuation.input_document(workflow_id),
            ),
            workflow_id=workflow_id,
            parent_step_id=continuation.parent_step_id,
        )
        controller = record.controller
        controller.begin_invocation(invocation, action)
        self._submit_invocation(
            workflow_id,
            invocation.invocation_id,
            lambda: self._execute_action.execute_follow_up_invocation(
                continuation,
                invocation,
                controller,
                binding=record.binding,
            ),
        )

    def _open_contextual_question(self) -> None:
        visible = self._visible_record()
        if visible is not None:
            workflow_id, record = visible
            focused = (
                self._user_control is not None
                and self._user_control.focused_surface == ControlSurfaceRef(workflow_id, "workflow")
            )
            if focused:
                if record.controller.request_question_composer() is not None:
                    self._foreground_id = workflow_id
                    self._request_attention(
                        workflow_id,
                        "想知道什麼？",
                        duration_ms=1200,
                        warning=False,
                    )
                else:
                    self._sequence_error("目前內容還不能提問。", "請等這次處理完成後再試一次。")
                return
            if record.controller.snapshot.pinned:
                self._sequence_error("目前視窗已固定。", "請先點選該視窗，再按 Ctrl+Alt+R 開啟問題欄。")
                return
        if self._input_resolver is None or self._supervisor is None:
            self._sequence_error("無法啟動「問這段」。", "請重新啟動 ClipAI 後再試一次。")
            return
        if not self._replace_unpinned_visible_workflow():
            self._sequence_error("目前視窗已固定。", "請在該視窗中直接使用問題輸入欄。")
            return

        workflow_id = uuid.uuid4().hex
        capture_id = uuid.uuid4().hex
        controller = self._new_controller(
            SessionSnapshot(
                workflow_id,
                0,
                SessionStatus.CREATED,
                CONTEXTUAL_QUESTION_ACTION_ID,
                "問這段",
                self._provider_configuration.active_binding.model,
                status_text="準備讀取內容…",
            ),
            "visible",
        )
        self._register(
            workflow_id,
            controller,
            self._provider_configuration.active_binding,
            "visible",
        )
        self._foreground_id = workflow_id
        token = controller.begin_contextual_source_capture(capture_id)
        resolver = self._input_resolver

        def capture() -> None:
            try:
                document = resolver.resolve_text(token)
            except InputError as error:
                self._enqueue(ContextualSourceCaptureFailed(workflow_id, capture_id, str(error)))
            except BaseException:
                self._enqueue(ContextualSourceCaptureFailed(
                    workflow_id,
                    capture_id,
                    "無法讀取反白或剪貼簿內容。",
                ))
            else:
                self._enqueue(ContextualSourceCaptured(workflow_id, capture_id, document))

        try:
            self._supervisor.submit(
                f"context-source:{capture_id}",
                capture,
                lambda _error: self._enqueue(ContextualSourceCaptureFailed(
                    workflow_id,
                    capture_id,
                    "無法讀取反白或剪貼簿內容。",
                )),
                task_class="interactive",
                cancellation_hook=token.cancel,
            )
        except BaseException:
            self._enqueue(ContextualSourceCaptureFailed(
                workflow_id,
                capture_id,
                "無法開始讀取反白或剪貼簿內容。",
            ))

    def _complete_contextual_source(self, command: ContextualSourceCaptured) -> None:
        record = self._records.get(command.workflow_id)
        if record is None or record.presentation != "visible":
            return
        try:
            completed = record.controller.complete_contextual_source_capture(
                command.capture_id,
                command.document,
            )
        except ValueError as error:
            self._fail_contextual_source(ContextualSourceCaptureFailed(
                command.workflow_id,
                command.capture_id,
                str(error),
            ))
            return
        if completed is not None:
            self._foreground_id = command.workflow_id

    def _fail_contextual_source(self, command: ContextualSourceCaptureFailed) -> None:
        record = self._records.get(command.workflow_id)
        if record is None or record.presentation != "visible":
            return
        if record.controller.fail_contextual_source_capture(command.capture_id, command.message) is None:
            return
        suggestion = (
            "請重新選取較小範圍的文字後再試一次。"
            if "太長" in command.message
            else "請先反白文字，或把文字複製到剪貼簿後再試一次。"
        )
        self._sequence_error(command.message, suggestion)
        self._end(command.workflow_id, "close")

    def _submit_contextual_question(self, command: SubmitContextualQuestion) -> None:
        record = self._records.get(command.workflow_id)
        if record is None or record.presentation != "visible" or not command.question.strip():
            return
        snapshot = record.controller.snapshot
        if (
            snapshot.status is not SessionStatus.CONTEXT_QUESTION
            or not snapshot.contextual_source_text
            or snapshot.contextual_source_kind not in {"selection", "clipboard"}
        ):
            return
        continuation = FollowUpContinuation.for_contextual_question(
            command.question.strip(),
            snapshot.contextual_source_text,
            snapshot.contextual_source_kind,
        )
        self._start_follow_up_continuation(record, continuation)

    def _cancel(self, session_id: str) -> None:
        self._end(session_id, "cancel")

    def _close(self, session_id: str) -> None:
        self._end(session_id, "close")

    def _handle_unhandled(self, session_id: str, error: BaseException) -> None:
        incident_id = self._incident_reporter.report(error, context=f"session:{session_id}")
        record = self._records.get(session_id)
        controller = record.controller if record is not None else None
        if controller:
            active_id = controller.snapshot.active_invocation_id
            if active_id is not None:
                controller.fail(active_id, f"ClipAI encountered an unexpected error. Incident: {incident_id}")
            if record is not None and record.presentation == "headless":
                self._end(session_id, "release")

    def _submit_invocation(
        self,
        workflow_id: str,
        invocation_id: str,
        work: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            if self._user_control is not None:
                record = self._records.get(workflow_id)
                lease = self._user_control.begin(InterruptibleOperationRef(
                    invocation_id,
                    "workflow",
                    workflow_id=workflow_id,
                    surface_id=workflow_id if record is not None and record.presentation == "visible" else "",
                ))
                self._interruption_leases[invocation_id] = lease

            async def tracked_work() -> None:
                try:
                    await work()
                finally:
                    current = self._interruption_leases.pop(invocation_id, None)
                    if current is not None:
                        current.finish()

            self._provider_execution.start(
                invocation_id,
                tracked_work,
                lambda _result: None,
                lambda error: self._enqueue(WorkflowInvocationFailed(workflow_id, error)),
                lambda: None,
            )
        except BaseException as error:
            self._handle_unhandled(workflow_id, error)

    def _finish_headless(self, workflow_id: str) -> None:
        record = self._records.get(workflow_id)
        if record is not None and record.presentation == "headless":
            self._end(workflow_id, "release")

    def _project_snapshot(self, snapshot: SessionSnapshot, presentation: WorkflowPresentation) -> None:
        record = self._records.get(snapshot.session_id)
        if record is not None and record.controller.snapshot.revision < snapshot.revision:
            return
        if presentation == "visible":
            self._view.render(snapshot)
        elif snapshot.status == SessionStatus.FAILED:
            self._sequence_error(snapshot.error, "Check the active model and try again.")

    def _foreground_context(self):
        workflow_id = self._foreground_id
        if workflow_id is None:
            return None
        record = self._records.get(workflow_id)
        if record is None or record.presentation != "visible":
            self._foreground_id = None
            return None
        context = self._workflow_context_reader.workflow_context(workflow_id)
        return context if context is not None and context.workflow_id == workflow_id else None

    def _register(
        self,
        workflow_id: str,
        controller: WorkflowController,
        binding: ProviderExecutionBinding,
        presentation: WorkflowPresentation,
        *,
        personal_style: PersonalStyleProfile | None = None,
    ) -> _WorkflowRecord:
        if workflow_id in self._records:
            raise RuntimeError(f"workflow identity is already registered: {workflow_id}")
        if presentation == "visible" and self._visible_record() is not None:
            raise RuntimeError("only one visible Workflow may own the popup")
        record = _WorkflowRecord(controller, binding, presentation, personal_style)
        self._records[workflow_id] = record
        return record

    def _visible_record(self) -> tuple[str, _WorkflowRecord] | None:
        for workflow_id, record in self._records.items():
            if record.presentation == "visible":
                return workflow_id, record
        return None

    def _record_accepted_step(self, command: WorkflowStepAccepted) -> None:
        if self._recent_actions is None:
            return
        record = self._records.get(command.workflow_id)
        if record is None:
            return
        steps = {step.step_id: step for step in record.controller.snapshot.steps}
        step = steps.get(command.step_id)
        if step is None:
            return
        root = step
        visited = {root.step_id}
        while root.parent_step_id is not None:
            parent = steps.get(root.parent_step_id)
            if parent is None or parent.step_id in visited:
                return
            root = parent
            visited.add(root.step_id)
        if not self._actions.contains(root.action_id):
            return
        refs = self._recent_actions.record(
            EntryActionRef(root.action_id, root.press_type)
        )
        if self._recent_action_sink is not None:
            self._recent_action_sink(refs)

    def _replace_unpinned_visible_workflow(self) -> bool:
        visible = self._visible_record()
        if visible is None:
            return True
        workflow_id, record = visible
        if record.controller.snapshot.pinned:
            return False
        self._end(workflow_id, "cancel")
        return True

    def _request_attention(
        self,
        workflow_id: str,
        message: str,
        *,
        duration_ms: int = 3000,
        warning: bool = True,
    ) -> None:
        attention_id = uuid.uuid4().hex
        self._pending_attention[workflow_id] = (attention_id, message)
        attention = WorkflowAttention(
            attention_id,
            workflow_id,
            message,
            duration_ms=duration_ms,
            warning=warning,
        )
        if self._attention_presenter is not None:
            self._attention_presenter.present_workflow_attention(attention)
        elif self._notifier is not None:
            self._notifier.notify("ClipAI", message)

    def _complete_attention(self, command: WorkflowAttentionCompleted) -> None:
        pending = self._pending_attention.get(command.workflow_id)
        if pending is None or pending[0] != command.attention_id:
            return
        self._pending_attention.pop(command.workflow_id, None)
        if not command.focus_acquired and self._notifier is not None:
            separator = "" if pending[1].endswith(("。", ".", "!", "？", "?")) else "。"
            self._notifier.notify(
                "ClipAI",
                f"{pending[1]}{separator}視窗未取得焦點，請先點選該視窗後再操作。",
            )

    def _end(
        self,
        workflow_id: str,
        disposition: Literal["cancel", "close", "release"],
        *,
        cancel_task: bool = True,
    ) -> None:
        record = self._records.pop(workflow_id, None)
        if record is None:
            return
        if self._foreground_id == workflow_id:
            self._foreground_id = None
        active_id = record.controller.snapshot.active_invocation_id
        capture_id = record.controller.snapshot.contextual_source_capture_id
        if disposition == "cancel":
            record.controller.cancel()
        elif disposition == "close":
            record.controller.close()
        if active_id is not None and cancel_task:
            self._provider_execution.cancel(active_id)
        if capture_id is not None and self._supervisor is not None:
            self._supervisor.cancel(f"context-source:{capture_id}")

    def _sequence_waiting(self) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_waiting()

    def _sequence_error(self, message: str, suggestion: str) -> None:
        if self._operation_tracker is not None:
            self._operation_tracker.report_error(message, suggestion)
        if self._notifier is not None:
            self._notifier.notify("ClipAI", " ".join(part for part in (message, suggestion) if part))
