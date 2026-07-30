from ClipAI.core.models import ControlSurfaceRef, InterruptibleOperationRef
from ClipAI.services.user_control import UserControlCoordinator


def test_current_operation_is_the_latest_still_registered_operation() -> None:
    coordinator = UserControlCoordinator()
    first = coordinator.begin(InterruptibleOperationRef("workflow-1", "workflow"))
    coordinator.begin(InterruptibleOperationRef("speech-1", "speech"))

    assert coordinator.interrupt_current().operations == (
        InterruptibleOperationRef("speech-1", "speech"),
    )

    first.finish()
    assert coordinator.interrupt_current().operations == ()


def test_focused_surface_claims_only_its_owned_operations() -> None:
    coordinator = UserControlCoordinator()
    surface = ControlSurfaceRef("popup-1", "workflow")
    coordinator.begin(InterruptibleOperationRef(
        "workflow-1", "workflow", workflow_id="popup-1", surface_id="popup-1"
    ))
    coordinator.begin(InterruptibleOperationRef("speech-1", "speech"))
    coordinator.focus(surface)

    plan = coordinator.interrupt_current()

    assert plan.surface == surface
    assert tuple(item.operation_id for item in plan.operations) == ("workflow-1",)
    assert coordinator.interrupt_current().operations[0].operation_id == "speech-1"


def test_global_interrupt_excludes_provider_configuration() -> None:
    coordinator = UserControlCoordinator()
    coordinator.begin(InterruptibleOperationRef("workflow-1", "workflow"))
    coordinator.begin(InterruptibleOperationRef(
        "settings-1", "provider_configuration", surface_id="provider-settings"
    ))

    assert tuple(item.operation_id for item in coordinator.interrupt_all().operations) == (
        "workflow-1",
    )
    assert coordinator.interrupt_current().operations[0].operation_id == "settings-1"
