from types import SimpleNamespace
import pytest

from ClipAI.app.runtime_interruption import InterruptionRuntimeModule
from ClipAI.core.commands import CloseSession, CloseProviderSettings, InterruptionRequested, InterruptCurrent, InterruptAll
from ClipAI.core.models import ControlSurfaceRef, InterruptibleOperationRef
from ClipAI.services.user_control import UserControlCoordinator


def harness(*, popup=None, panel_claim=False, inline_claim=False):
    events = []
    control = UserControlCoordinator()
    workflows = SimpleNamespace(
        handle=lambda command: events.append(("workflow", command.session_id, control.focused_surface)),
        has_pending_shortcut_sequence=lambda: False,
        cancel_shortcut_sequence=lambda: events.append("sequence"),
        unpinned_foreground_popup_id=lambda: popup,
        cancel_all_content_operations=lambda: events.append("workflow_all") or ("w-task",),
        cancel_operation=lambda operation_id: events.append(("workflow_cancel", operation_id)),
    )
    outputs = SimpleNamespace(
        close_workflow=lambda identity: events.append(("output", identity)),
        cancel_all_content_operations=lambda: events.append("output_all") or ("o-task",),
        cancel_operation=lambda operation_id: events.append(("output_cancel", operation_id)),
    )
    voice = SimpleNamespace(
        close_workflow=lambda identity: events.append(("voice", identity)),
        cancel_inline_dictation=lambda: events.append("inline") or inline_claim,
    )
    module = InterruptionRuntimeModule(
        user_control=control, workflows=workflows, result_output=outputs,
        voice_input=voice,
        entry_panel=SimpleNamespace(request_escape=lambda: events.append("panel") or panel_claim),
        provider_configuration=SimpleNamespace(handle=lambda command: events.append(command)),
        supervisor=SimpleNamespace(cancel_many=lambda ids, done: events.append(("tasks", ids))),
        route=lambda command: events.append(("route", command)),
    )
    return module, control, events


def test_close_releases_user_control_before_voice_output_and_workflow():
    module, control, events = harness()
    control.focus(ControlSurfaceRef("w", "workflow"))
    module.handle(CloseSession("w"))
    assert events == [("voice", "w"), ("output", "w"), ("workflow", "w", None)]


@pytest.mark.parametrize("command", [InterruptCurrent(), InterruptionRequested("current")])
def test_panel_claims_current_before_inline(command):
    module, _, events = harness(panel_claim=True, inline_claim=True)
    module.handle(command)
    assert events == ["panel"]


def test_inline_claims_current_before_focused_popup():
    module, control, events = harness(inline_claim=True)
    control.focus(ControlSurfaceRef("w", "workflow"))
    module.handle(InterruptCurrent())
    assert events == ["panel", "inline"]
    assert control.focused_surface == ControlSurfaceRef("w", "workflow")


@pytest.mark.parametrize("popup", [None, "unpinned"])
def test_only_existing_unpinned_foreground_popup_is_closed_as_fallback(popup):
    module, _, events = harness(popup=popup)
    module.handle(InterruptCurrent())
    expected = ["panel", "inline"]
    if popup:
        expected += [("voice", popup), ("output", popup), ("workflow", popup, None)]
    assert events == expected


def test_all_skips_panel_and_cancels_inline_before_content_tasks():
    module, _, events = harness(panel_claim=True)
    module.handle(InterruptAll())
    assert events == ["inline", "workflow_all", "output_all", ("tasks", ("w-task", "o-task"))]


def test_focused_nonworkflow_surface_closes_through_synchronous_router():
    module, control, events = harness()
    control.focus(ControlSurfaceRef("settings", "provider_settings"))
    module.handle(InterruptCurrent())
    assert events == ["panel", "inline", ("route", CloseProviderSettings())]


def test_latest_operation_is_interrupted_before_unpinned_popup_fallback():
    module, control, events = harness(popup="w")
    control.begin(InterruptibleOperationRef("old", "workflow"))
    control.begin(InterruptibleOperationRef("new", "speech"))
    module.handle(InterruptCurrent())
    assert events == ["panel", "inline", ("output_cancel", "new")]
