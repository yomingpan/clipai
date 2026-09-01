from __future__ import annotations

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.runtime_entry_panel import EntryPanelRuntimeModule
from ClipAI.core.commands import EntryPanelToggleDensity, RetryEntryPanelInput, SetEntryPanelDensity
from ClipAI.core.models import (
    ActionStartAdmission,
    ActiveWorkflowContext,
    EntryActionRef,
    ExternalWindowActivationOutcome,
    ExternalWindowRef,
    InputDocument,
    PreparedEntryInput,
)
from ClipAI.services.entry_panel import EntryPanelCoordinator


class Presenter:
    def __init__(self, events: list[str] | None = None) -> None:
        self.snapshots = []
        self.popup_transitions = []
        self.events = events

    def present_entry_panel(self, snapshot) -> None:
        self.snapshots.append(snapshot)
        if self.events is not None:
            self.events.append("panel:presented")

    def transition_entry_panel_to_popup(self, panel_id, workflow_id) -> None:
        self.popup_transitions.append((panel_id, workflow_id))


class Supervisor:
    def __init__(self) -> None:
        self.work = {}
        self.cancelled = []
        self.task_classes = {}

    def submit(self, task_id, work, on_unhandled_error, *, task_class="interactive", cancellation_hook=None):
        del on_unhandled_error, cancellation_hook
        self.work[task_id] = work
        self.task_classes[task_id] = task_class

    def cancel(self, task_id) -> None:
        self.cancelled.append(task_id)


class Workflows:
    def __init__(self, *, foreground_workflow_id=None, block_reason="") -> None:
        self.foreground_workflow_id = foreground_workflow_id
        self.block_reason = block_reason
        self.starts = []

    def start_action(
        self,
        action_id,
        press_type,
        *,
        result_route="popup",
        input_target=None,
        admission_origin="shortcut",
        before_first_projection=None,
    ):
        self.starts.append((action_id, press_type, result_route, input_target, admission_origin))
        if before_first_projection is not None:
            before_first_projection("workflow-1")
        return ActionStartAdmission("accepted", workflow_id="workflow-1")

    def entry_panel_action_block_reason(self, _action):
        return self.block_reason


class Activator:
    def __init__(self, outcome=ExternalWindowActivationOutcome("activated")) -> None:
        self.outcome = outcome
        self.targets = []

    def activate(self, target, cancellation):
        del cancellation
        self.targets.append(target)
        return self.outcome

    def confirm(self, _target):
        return self.outcome


class Inputs:
    def __init__(self, prepared: PreparedEntryInput | None = None) -> None:
        self.prepared = prepared or PreparedEntryInput(
            selection_document=InputDocument("selected at open", "selection")
        )
        self.calls = 0

    def prepare_entry_input(self, cancellation=None):
        del cancellation
        self.calls += 1
        return self.prepared


def make_module(
    *,
    activation_outcome=ExternalWindowActivationOutcome("activated"),
    foreground_workflow_id=None,
    workflow_context=None,
    external_window_activator=None,
    input_resolver=None,
    supervisor=None,
    events: list[str] | None = None,
):
    bundle = load_config_bundle()
    coordinator = EntryPanelCoordinator(bundle.entry_panel)
    presenter = Presenter(events)
    supervisor = supervisor or Supervisor()
    workflows = Workflows(foreground_workflow_id=foreground_workflow_id)
    activator = external_window_activator or Activator(activation_outcome)
    inputs = input_resolver or Inputs()
    commands = []
    external = ExternalWindowRef("hwnd:10", 42, 7)

    def read_external():
        if events is not None:
            events.append("source:captured")
        return external

    module = EntryPanelRuntimeModule(
        coordinator=coordinator,
        actions=bundle.actions,
        workflows=workflows,
        workflow_context_reader=lambda _workflow_id: workflow_context,
        external_source_reader=read_external,
        external_window_activator=activator,
        input_resolver=inputs,
        supervisor=supervisor,
        enqueue=commands.append,
        presenter=presenter,
    )
    return module, coordinator, presenter, supervisor, workflows, activator, inputs, commands, external


def complete_external_preparation(module, supervisor, commands) -> str:
    task_id = next(reversed(supervisor.work))
    supervisor.work[task_id]()
    module.handle(commands.pop(0))
    return task_id


def test_external_source_is_captured_before_panel_and_work_starts_after_projection() -> None:
    events: list[str] = []
    module, _coordinator, _presenter, supervisor, _workflows, _activator, inputs, _commands, _external = make_module(events=events)

    snapshot = module.open()

    assert events == ["source:captured", "panel:presented"]
    assert snapshot.status == "preparing"
    assert snapshot.source_preview.kind == "preparing"
    assert inputs.calls == 0
    task_id = next(iter(supervisor.work))
    assert supervisor.task_classes[task_id] == "interactive"


def test_preparation_submission_failure_is_projected_as_retryable_error() -> None:
    class FailingSupervisor(Supervisor):
        def submit(self, *args, **kwargs):
            del args, kwargs
            raise RuntimeError("interactive lane unavailable")

    module, coordinator, _presenter, _supervisor, _workflows, _activator, _inputs, commands, _external = make_module(
        supervisor=FailingSupervisor()
    )

    panel_id = module.open().panel_id
    module.handle(commands.pop())

    snapshot = coordinator.snapshot
    assert snapshot is not None
    assert snapshot.panel_id == panel_id
    assert snapshot.status == "error"
    assert snapshot.message == "Input preparation could not start."
    assert snapshot.source_preview.kind == "failed"


def test_external_input_is_frozen_at_open_and_selection_never_recaptures() -> None:
    inputs = Inputs()
    module, coordinator, presenter, supervisor, workflows, activator, _inputs, commands, external = make_module(input_resolver=inputs)
    panel_id = module.open().panel_id
    complete_external_preparation(module, supervisor, commands)
    inputs.prepared = PreparedEntryInput(
        selection_document=InputDocument("changed later", "selection")
    )

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert inputs.calls == 1
    assert activator.targets == [external]
    assert workflows.starts[-1][3].document == InputDocument(
        "selected at open", "selection"
    )
    assert workflows.starts[-1][4] == "entry_panel"
    assert coordinator.snapshot is None
    assert presenter.popup_transitions == [(panel_id, "workflow-1")]


def test_handoff_registration_still_precedes_first_popup_projection() -> None:
    module, coordinator, presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module()
    events: list[str] = []

    presenter.transition_entry_panel_to_popup = lambda _panel, _workflow: events.append("handoff:registered")

    def start_action(
        _action_id,
        _press_type,
        *,
        result_route="popup",
        input_target=None,
        admission_origin="shortcut",
        before_first_projection=None,
    ):
        del result_route, input_target, admission_origin
        before_first_projection("workflow-1")
        events.append("popup:first-projection")
        return ActionStartAdmission("accepted", workflow_id="workflow-1")

    workflows.start_action = start_action
    module.open()
    complete_external_preparation(module, supervisor, commands)

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert coordinator.snapshot is None
    assert events == ["handoff:registered", "popup:first-projection"]


def test_external_capture_retries_the_complete_preparation_after_focus_loss() -> None:
    class FocusAwareActivator:
        def __init__(self) -> None:
            self.foreground = False
            self.activations = 0

        def activate(self, _target, _cancellation):
            self.activations += 1
            self.foreground = True
            return ExternalWindowActivationOutcome("activated")

        def confirm(self, _target):
            if self.foreground:
                return ExternalWindowActivationOutcome("activated")
            return ExternalWindowActivationOutcome("target_changed", "target changed")

    class FocusSensitiveInputs(Inputs):
        def __init__(self, activator: FocusAwareActivator) -> None:
            super().__init__()
            self.activator = activator

        def prepare_entry_input(self, cancellation=None):
            prepared = super().prepare_entry_input(cancellation)
            if self.calls == 1:
                self.activator.foreground = False
                return PreparedEntryInput(
                    clipboard_text_document=InputDocument("untrusted", "clipboard")
                )
            return prepared

    activator = FocusAwareActivator()
    inputs = FocusSensitiveInputs(activator)
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module(
        external_window_activator=activator,
        input_resolver=inputs,
    )
    module.open()

    complete_external_preparation(module, supervisor, commands)
    module.select_action(EntryActionRef("shorten_content", "short"))

    assert coordinator.snapshot is None
    assert activator.activations == 2
    assert inputs.calls == 2
    assert workflows.starts[-1][3].document == InputDocument(
        "selected at open", "selection"
    )


def test_external_capture_fails_closed_after_two_focus_losses() -> None:
    class UnstableActivator:
        def __init__(self) -> None:
            self.activations = 0

        def activate(self, _target, _cancellation):
            self.activations += 1
            return ExternalWindowActivationOutcome("activated")

        def confirm(self, _target):
            return ExternalWindowActivationOutcome("target_changed", "target changed")

    activator = UnstableActivator()
    inputs = Inputs(
        PreparedEntryInput(
            clipboard_text_document=InputDocument("untrusted", "clipboard")
        )
    )
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module(
        external_window_activator=activator,
        input_resolver=inputs,
    )
    module.open()

    complete_external_preparation(module, supervisor, commands)

    assert coordinator.snapshot.status == "error"
    assert coordinator.snapshot.source_preview.kind == "failed"
    assert activator.activations == 2
    assert inputs.calls == 2
    assert workflows.starts == []


def test_retry_gets_new_identity_and_reuses_the_original_external_target() -> None:
    activator = Activator(
        ExternalWindowActivationOutcome("target_gone", "target unavailable")
    )
    module, coordinator, _presenter, supervisor, _workflows, _activator, _inputs, commands, external = make_module(
        external_window_activator=activator
    )
    panel_id = module.open().panel_id
    first_task = complete_external_preparation(module, supervisor, commands)
    activator.outcome = ExternalWindowActivationOutcome("activated")

    module.handle(RetryEntryPanelInput(panel_id))
    second_task = next(reversed(supervisor.work))
    complete_external_preparation(module, supervisor, commands)

    assert first_task != second_task
    assert activator.targets == [external, external]
    assert coordinator.snapshot.status == "idle"
    assert coordinator.snapshot.source_preview.kind == "selection_text"


def test_closed_or_reopened_panel_ignores_late_completion() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module()
    first_panel = module.open().panel_id
    first_task = next(iter(supervisor.work))
    module.close(first_panel)
    second_panel = module.open().panel_id

    supervisor.work[first_task]()
    module.handle(commands.pop(0))

    assert coordinator.snapshot.panel_id == second_panel
    assert coordinator.snapshot.status == "preparing"
    assert first_task in supervisor.cancelled
    assert workflows.starts == []


def test_popup_selection_is_frozen_at_open_with_exact_lineage() -> None:
    context = ActiveWorkflowContext(
        "workflow-1", "step-1", "full result", "selected popup text"
    )
    module, coordinator, presenter, supervisor, workflows, activator, inputs, commands, _external = make_module(
        foreground_workflow_id="workflow-1",
        workflow_context=context,
    )
    panel_id = module.open().panel_id
    module.handle(commands.pop(0))

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert workflows.starts[-1][3].document == InputDocument(
        "selected popup text", "workflow_result", "workflow-1", "step-1"
    )
    assert activator.targets == []
    assert inputs.calls == 0
    assert supervisor.work == {}
    assert coordinator.snapshot is None
    assert presenter.popup_transitions == [(panel_id, "workflow-1")]


def test_popup_canonical_content_is_frozen_when_selection_is_empty() -> None:
    context = ActiveWorkflowContext("workflow-1", "step-2", "full result", "  ")
    module, _coordinator, _presenter, _supervisor, workflows, _activator, _inputs, commands, _external = make_module(
        foreground_workflow_id="workflow-1",
        workflow_context=context,
    )
    module.open()
    module.handle(commands.pop(0))

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert workflows.starts[-1][3].document == InputDocument(
        "full result", "workflow_result", "workflow-1", "step-2"
    )


def test_provider_busy_still_prepares_but_never_queues_an_action() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, inputs, commands, _external = make_module()
    workflows.block_reason = "AI 正在回答，完成後再選擇功能。"
    module.open()
    complete_external_preparation(module, supervisor, commands)
    scene = coordinator.select_digit("4").snapshot

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert inputs.calls == 1
    assert all(not option.enabled for option in scene.options)
    assert workflows.starts == []


def test_mode_compatibility_disables_only_incompatible_actions() -> None:
    inputs = Inputs(
        PreparedEntryInput(
            clipboard_text_document=InputDocument("clipboard text", "clipboard")
        )
    )
    module, coordinator, _presenter, supervisor, _workflows, _activator, _inputs, commands, _external = make_module(
        input_resolver=inputs
    )
    module.open()
    complete_external_preparation(module, supervisor, commands)

    tools_scene = coordinator.select_digit("6").snapshot
    ocr = next(
        option
        for option in tools_scene.options
        if option.action == EntryActionRef("extract_screenshot_text", "short")
    )
    text_action = next(
        option
        for option in tools_scene.options
        if option.action == EntryActionRef("session_handoff", "short")
    )

    assert ocr.enabled is False
    assert "截圖" in ocr.disabled_reason
    assert text_action.enabled is True


def test_action_rechecks_runtime_availability_at_selection_intent() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module()
    module.open()
    complete_external_preparation(module, supervisor, commands)
    workflows.block_reason = "AI 正在回答，完成後再選擇功能。"

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert coordinator.snapshot.status == "error"
    assert "AI 正在回答" in coordinator.snapshot.message
    assert workflows.starts == []


def test_availability_refresh_preserves_navigation_and_frozen_input() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module()
    module.open()
    complete_external_preparation(module, supervisor, commands)
    before = coordinator.select_digit("4").snapshot
    workflows.block_reason = "AI 正在回答，完成後再選擇功能。"

    module.refresh_availability()

    after = coordinator.snapshot
    assert after.page == before.page
    assert after.category_id == before.category_id
    assert after.source_preview == before.source_preview
    assert all(not option.enabled for option in after.options)


def test_density_toggle_projects_immediately_and_requests_persistence() -> None:
    module, coordinator, presenter, _supervisor, _workflows, _activator, _inputs, commands, _external = make_module()
    panel_id = module.open().panel_id

    module.handle(EntryPanelToggleDensity(panel_id))

    assert coordinator.snapshot.density == "compact"
    assert presenter.snapshots[-1].density == "compact"
    assert commands[-1] == SetEntryPanelDensity("compact")
