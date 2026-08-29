from __future__ import annotations

from ClipAI.core.commands import CloseSession, CopyResult, EntryPanelDigitPressed, OpenUnifiedEntryPanel, SelectProviderModel, SetFirstUseHintsEnabled, StartAction
from ClipAI.core.models import ModifierHoldId, UserPreferences
from ClipAI.services.user_preferences import UserPreferencesCoordinator
from tests.app.test_runtime import GuidanceStore, ModelPreferences, make_runtime


def test_workflow_module_interface_owns_workflow_creation() -> None:
    runtime, view, supervisor, _outputs, _listener = make_runtime()

    runtime._workflow_module.handle(StartAction("a", "short"))
    runtime.drain_commands()

    workflow_id = view.snapshots[-1].session_id
    controller = runtime._workflow_module.controller_for(workflow_id)
    assert controller is not None
    assert runtime._workflow_module.has_foreground_workflow()
    assert controller.snapshot.active_invocation_id in supervisor.work


def test_result_output_module_interface_uses_canonical_workflow_result() -> None:
    runtime, view, supervisor, outputs, _listener = make_runtime()
    runtime._workflow_module.handle(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = runtime._workflow_module.controller_for(workflow_id)
    assert controller is not None
    controller._snapshot = controller.snapshot.evolve(content="canonical result")

    runtime._result_output_module.handle(CopyResult(workflow_id, operation_id="copy-op"))
    supervisor.work["copy-op"]()

    assert outputs.copied == ["canonical result"]


def test_provider_configuration_module_interface_projects_committed_selection() -> None:
    preferences = ModelPreferences()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(model_preferences=preferences)

    runtime._provider_configuration_module.handle(SelectProviderModel("openai", "new-model"))

    assert preferences.saved == [("OPENAI_MODEL", "new-model")]
    assert runtime._provider_configuration_module.coordinator.active_binding.model == "new-model"


def test_user_preferences_module_interface_waits_for_completion_projection() -> None:
    store = GuidanceStore(UserPreferences(False))
    guidance = UserPreferencesCoordinator(store)
    runtime, _view, supervisor, _outputs, _listener = make_runtime(
        guidance_preferences=guidance,
        guidance_preferences_presenter=None,
    )

    runtime._user_preferences_module.handle(SetFirstUseHintsEnabled(True, "guidance-op"))
    assert guidance.guidance_preferences.first_use_hints_enabled is False

    supervisor.work["guidance-preferences:guidance-op"]()
    runtime.drain_commands()

    assert guidance.guidance_preferences.first_use_hints_enabled is True


def test_runtime_routes_close_output_cleanup_before_workflow_close() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    calls = []
    runtime._result_output_module.close_workflow = lambda workflow_id: calls.append(("output", workflow_id))
    runtime._workflow_module.handle = lambda command: calls.append(("workflow", command.session_id))

    runtime.enqueue(CloseSession("workflow-1"))
    runtime.drain_commands()

    assert calls == [("output", "workflow-1"), ("workflow", "workflow-1")]


def test_runtime_routes_entry_panel_commands_to_its_independent_module() -> None:
    commands = []

    class EntryPanel:
        def handle(self, command) -> None:
            commands.append(command)

        def stop(self) -> None:
            pass

    panel = EntryPanel()
    runtime, _view, _supervisor, _outputs, _listener = make_runtime(entry_panel=panel)
    opened = OpenUnifiedEntryPanel(ModifierHoldId(1))
    digit = EntryPanelDigitPressed(ModifierHoldId(1), "3")

    runtime.enqueue(opened)
    runtime.enqueue(digit)
    runtime.drain_commands()

    assert commands == [opened, digit]
