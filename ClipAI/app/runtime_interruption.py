from __future__ import annotations

from collections.abc import Callable

from ClipAI.app.runtime_entry_panel import EntryPanelRuntimeModule
from ClipAI.app.runtime_outputs import ResultOutputRuntimeModule
from ClipAI.app.runtime_provider_configuration import ProviderConfigurationRuntimeModule
from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import CloseSession, CloseProviderSettings, CloseShortcutGuide, ClosePersonalStyles, InterruptionRequested, InterruptAll, InterruptCurrent
from ClipAI.core.models import ControlSurfaceRef, InterruptionPlan
from ClipAI.services.user_control import UserControlCoordinator


class InterruptionRuntimeModule:
    """Owns interruption ordering across desktop use cases."""

    def __init__(
        self, *, user_control: UserControlCoordinator,
        workflows: WorkflowRuntimeModule, result_output: ResultOutputRuntimeModule,
        provider_configuration: ProviderConfigurationRuntimeModule,
        supervisor: TaskSupervisor, route: Callable[[object], None],
        voice_input: VoiceInputRuntimeModule | None = None,
        entry_panel: EntryPanelRuntimeModule | None = None,
    ) -> None:
        self._user_control = user_control
        self._workflows = workflows
        self._outputs = result_output
        self._provider_configuration = provider_configuration
        self._supervisor = supervisor
        self._route = route
        self._voice = voice_input
        self._panel = entry_panel

    def handle(self, command: CloseSession | InterruptionRequested | InterruptCurrent | InterruptAll) -> None:
        if isinstance(command, CloseSession):
            self._user_control.release(ControlSurfaceRef(command.session_id, "workflow"))
            if self._voice is not None:
                self._voice.close_workflow(command.session_id)
            self._outputs.close_workflow(command.session_id)
            self._workflows.handle(command)
        elif isinstance(command, InterruptAll) or isinstance(command, InterruptionRequested) and command.scope == "all":
            if self._voice is not None:
                self._voice.cancel_inline_dictation()
            self._execute(self._user_control.interrupt_all())
            tasks = (*self._workflows.cancel_all_content_operations(), *self._outputs.cancel_all_content_operations())
            self._supervisor.cancel_many(tasks, lambda: None)
        else:
            if self._panel is not None and self._panel.request_escape():
                return
            if self._voice is not None and self._voice.cancel_inline_dictation():
                return
            if self._user_control.focused_surface is None and self._workflows.has_pending_shortcut_sequence():
                self._workflows.cancel_shortcut_sequence()
                return
            plan = self._user_control.interrupt_current()
            if plan.surface is None and not plan.operations:
                popup = self._workflows.unpinned_foreground_popup_id()
                if popup is not None:
                    self.handle(CloseSession(popup))
                    return
            self._execute(plan)

    def _execute(self, plan: InterruptionPlan) -> None:
        surface = plan.surface
        if surface is not None:
            if surface.kind == "workflow":
                self.handle(CloseSession(surface.surface_id))
            elif surface.kind == "provider_settings":
                self._route(CloseProviderSettings())
            elif surface.kind == "shortcut_guide":
                self._route(CloseShortcutGuide(surface.surface_id))
            elif surface.kind == "personal_styles":
                self._route(ClosePersonalStyles())
        for operation in plan.operations:
            if operation.kind == "workflow":
                self._workflows.cancel_operation(operation.operation_id)
            elif operation.kind == "provider_configuration":
                self._provider_configuration.handle(CloseProviderSettings())
            elif operation.kind == "shortcut_sequence":
                self._workflows.cancel_shortcut_sequence()
            else:
                self._outputs.cancel_operation(operation.operation_id)
