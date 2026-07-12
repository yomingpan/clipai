from ClipAI.services.workflow_registry import WorkflowRegistry


def test_registry_owns_foreground_and_sequence_identity() -> None:
    registry = WorkflowRegistry()
    controller = object()
    registry.add("w", controller, foreground=True)  # type: ignore[arg-type]
    registry.sequence_id = "w"
    assert registry.get("w") is controller
    registry.remove("w")
    assert registry.foreground_id is None
    assert registry.sequence_id is None
