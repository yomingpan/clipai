from ClipAI.app.config_loader import load_action_catalog, load_entry_panel_catalog
from ClipAI.app.runtime_entry_panel import EntryPanelRuntimeModule
from ClipAI.core.commands import EntryPanelToggleDensity, SetEntryPanelDensity
from ClipAI.core.models import (
    ActionStartAdmission,
    ActiveWorkflowContext,
    EntryActionRef,
    ExternalWindowActivationOutcome,
    ExternalWindowRef,
    InputDocument,
)
from ClipAI.services.entry_panel import EntryPanelCoordinator


class Presenter:
    def __init__(self) -> None:
        self.snapshots = []

    def present_entry_panel(self, snapshot) -> None:
        self.snapshots.append(snapshot)


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
    ):
        self.starts.append((action_id, press_type, result_route, input_target, admission_origin))
        return ActionStartAdmission("accepted")

    def entry_panel_action_block_reason(self, _action):
        return self.block_reason


class Activator:
    def __init__(self, outcome=ExternalWindowActivationOutcome("activated")) -> None:
        self.outcome = outcome
        self.targets = []

    def activate(self, target, cancellation):
        self.targets.append(target)
        return self.outcome


class Inputs:
    def __init__(self) -> None:
        self.documents = []

    def resolve(self, mode, cancellation=None):
        del cancellation
        document = InputDocument("selected at intent", "selection")
        self.documents.append((mode, document))
        return document


def make_module(
    *,
    activation_outcome=ExternalWindowActivationOutcome("activated"),
    foreground_workflow_id=None,
    workflow_context=None,
):
    actions = load_action_catalog("config/actions.yaml")
    coordinator = EntryPanelCoordinator(load_entry_panel_catalog(
        "config/entry_panel.yaml",
        actions=actions,
    ))
    presenter = Presenter()
    supervisor = Supervisor()
    workflows = Workflows(foreground_workflow_id=foreground_workflow_id)
    activator = Activator(activation_outcome)
    inputs = Inputs()
    commands = []
    external = ExternalWindowRef("hwnd:10", 42, 7)
    module = EntryPanelRuntimeModule(
        coordinator=coordinator,
        actions=actions,
        workflows=workflows,
        workflow_context_reader=lambda _workflow_id: workflow_context,
        external_source_reader=lambda: external,
        external_window_activator=activator,
        input_resolver=inputs,
        supervisor=supervisor,
        enqueue=commands.append,
        presenter=presenter,
    )
    return module, coordinator, presenter, supervisor, workflows, activator, inputs, commands, external


def test_external_action_restores_exact_source_then_admits_prepared_input() -> None:
    module, coordinator, presenter, supervisor, workflows, activator, inputs, commands, external = make_module()
    module.open()

    module.select_action(EntryActionRef("shorten_content", "short"))

    pending = coordinator.snapshot
    assert pending.status == "preparing"
    task_id = next(iter(supervisor.work))
    assert supervisor.task_classes[task_id] == "interactive"
    supervisor.work[task_id]()
    module.handle(commands.pop())

    assert activator.targets == [external]
    assert inputs.documents
    assert workflows.starts[-1][3].document.text == "selected at intent"
    assert workflows.starts[-1][4] == "entry_panel"
    assert coordinator.snapshot is None
    assert presenter.snapshots[-1] is None


def test_closed_panel_ignores_late_input_preparation_completion() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, commands, _external = make_module()
    panel_id = module.open().panel_id
    module.select_action(EntryActionRef("shorten_content", "short"))
    task_id = next(iter(supervisor.work))

    module.close(panel_id)
    supervisor.work[task_id]()
    module.handle(commands.pop())

    assert coordinator.snapshot is None
    assert task_id in supervisor.cancelled
    assert workflows.starts == []


def test_external_activation_failure_keeps_panel_and_does_not_capture_input() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, inputs, commands, _external = make_module(
        activation_outcome=ExternalWindowActivationOutcome(
            "target_gone",
            "The original window is no longer available.",
        )
    )
    module.open()
    module.select_action(EntryActionRef("shorten_content", "short"))

    supervisor.work[next(iter(supervisor.work))]()
    module.handle(commands.pop())

    assert coordinator.snapshot.status == "error"
    assert "original window" in coordinator.snapshot.message
    assert inputs.documents == []
    assert workflows.starts == []


def test_popup_source_reuses_current_semantic_selection_without_external_capture() -> None:
    context = ActiveWorkflowContext(
        "workflow-1",
        "step-1",
        "full result",
        "selected popup text",
    )
    module, coordinator, _presenter, supervisor, workflows, activator, inputs, commands, _external = make_module(
        foreground_workflow_id="workflow-1",
        workflow_context=context,
    )
    module.open()

    module.select_action(EntryActionRef("shorten_content", "short"))
    module.handle(commands.pop())

    target = workflows.starts[-1][3]
    assert target.kind == "workflow_result"
    assert target.document.text == "selected popup text"
    assert target.document.workflow_id == "workflow-1"
    assert target.document.step_id == "step-1"
    assert workflows.starts[-1][4] == "entry_panel"
    assert activator.targets == []
    assert inputs.documents == []
    assert supervisor.work == {}
    assert coordinator.snapshot is None


def test_known_runtime_unavailability_keeps_actions_visible_and_disabled() -> None:
    module, coordinator, _presenter, _supervisor, workflows, _activator, _inputs, _commands, _external = make_module()
    workflows.block_reason = "AI 正在回答，完成後再選擇功能。"

    module.open()
    scene = coordinator.select_digit("4").snapshot

    assert scene.options
    assert all(not option.enabled for option in scene.options)
    assert all("AI 正在回答" in option.disabled_reason for option in scene.options)


def test_action_rechecks_runtime_availability_at_selection_intent() -> None:
    module, coordinator, _presenter, supervisor, workflows, _activator, _inputs, _commands, _external = make_module()
    module.open()
    workflows.block_reason = "AI 正在回答，完成後再選擇功能。"

    module.select_action(EntryActionRef("shorten_content", "short"))

    assert coordinator.snapshot.status == "error"
    assert "AI 正在回答" in coordinator.snapshot.message
    assert supervisor.work == {}


def test_availability_refresh_updates_open_options_without_navigation_reset() -> None:
    module, coordinator, _presenter, _supervisor, workflows, _activator, _inputs, _commands, _external = make_module()
    module.open()
    before = coordinator.select_digit("4").snapshot
    workflows.block_reason = "AI 正在回答，完成後再選擇功能。"

    module.refresh_availability()

    after = coordinator.snapshot
    assert after.page == before.page
    assert after.category_id == before.category_id
    assert all(not option.enabled for option in after.options)


def test_density_toggle_projects_immediately_and_requests_preference_persistence() -> None:
    module, coordinator, presenter, _supervisor, _workflows, _activator, _inputs, commands, _external = make_module()
    panel_id = module.open().panel_id

    module.handle(EntryPanelToggleDensity(panel_id))

    assert coordinator.snapshot.density == "compact"
    assert presenter.snapshots[-1].density == "compact"
    assert commands == [SetEntryPanelDensity("compact")]
