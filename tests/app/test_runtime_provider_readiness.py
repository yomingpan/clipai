from dataclasses import replace
import pytest

from ClipAI.core.commands import OpenProviderSettings, ReloadConfiguration, ValidateAndSaveProviderSettings
from ClipAI.core.models import ProviderSettingsInput, ReadinessIssue
from ClipAI.services.operation_lifecycle import OperationLifecycleCoordinator
from tests.app.test_runtime import make_runtime
from tests.services.test_operation_lifecycle import Indicator, Scheduler


def test_first_provider_save_restores_ready_tray_without_restart():
    indicator = Indicator()
    tracker = OperationLifecycleCoordinator(indicator, ready=False, schedule=Scheduler())
    runtime, view, supervisor, _, _ = make_runtime(operation_tracker=tracker)
    ready_snapshot = runtime._provider_backend.snapshot
    runtime._provider_backend.snapshot = replace(
        ready_snapshot,
        bindings=tuple(replace(binding, readiness_issues=(ReadinessIssue("missing", "Missing key", "llm"),))
                       for binding in ready_snapshot.bindings),
        options=tuple(replace(option, configured=False) for option in ready_snapshot.options),
    )
    runtime.enqueue(OpenProviderSettings())
    runtime.drain_commands()
    assert indicator.statuses[-1] == "warning"
    runtime._provider_backend.build = lambda *_: ready_snapshot
    runtime.enqueue(ValidateAndSaveProviderSettings(
        ProviderSettingsInput("openai", "model", "fixture-key"), "first-save"))
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_state == "pending"
    assert indicator.statuses[-1] == "warning"
    supervisor.work["provider-settings:first-save"]()
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_state == "succeeded"
    assert indicator.statuses[-1] == "idle"


@pytest.mark.parametrize("command", [OpenProviderSettings(), ReloadConfiguration()])
def test_accepted_provider_reload_updates_readiness(command):
    indicator = Indicator()
    tracker = OperationLifecycleCoordinator(indicator, ready=False, schedule=Scheduler())
    runtime, _, _, _, _ = make_runtime(operation_tracker=tracker)
    runtime.enqueue(command)
    runtime.drain_commands()
    assert indicator.statuses[-1] == "idle"


def test_readiness_projection_does_not_clear_active_work_or_sticky_error():
    indicator, scheduler = Indicator(), Scheduler()
    tracker = OperationLifecycleCoordinator(indicator, ready=False, schedule=scheduler)
    runtime, _, _, _, _ = make_runtime(operation_tracker=tracker)
    operation = tracker.start("work", "llm")
    runtime.enqueue(ReloadConfiguration())
    runtime.drain_commands()
    assert indicator.statuses[-1] == "processing"
    operation.succeed()
    runtime.enqueue(ReloadConfiguration())
    runtime.drain_commands()
    assert indicator.statuses[-1] == "success"
    scheduler.calls[-1].fire()
    assert indicator.statuses[-1] == "idle"
    tracker.report_error("Actual failure")
    runtime.enqueue(OpenProviderSettings())
    runtime.drain_commands()
    assert indicator.statuses[-1] == "error"


def test_failed_provider_save_does_not_report_ready():
    indicator = Indicator()
    tracker = OperationLifecycleCoordinator(indicator, ready=False, schedule=Scheduler())
    def reject(*_):
        raise ValueError("fixture validation failure")
    runtime, view, supervisor, _, _ = make_runtime(operation_tracker=tracker, validate_provider_credential=reject)
    snapshot = runtime._provider_backend.snapshot
    runtime._provider_backend.snapshot = replace(snapshot, bindings=tuple(
        replace(binding, readiness_issues=(ReadinessIssue("missing", "Missing key", "llm"),))
        for binding in snapshot.bindings))
    runtime.enqueue(OpenProviderSettings())
    runtime.enqueue(ValidateAndSaveProviderSettings(ProviderSettingsInput("openai", "model", "fixture"), "failed-save"))
    runtime.drain_commands()
    supervisor.work["provider-settings:failed-save"]()
    runtime.drain_commands()
    assert view.provider_settings_states[-1].operation_state == "failed"
    assert indicator.statuses[-1] != "idle"
    tracker.stop()
    assert indicator.statuses[-1] == "warning"
