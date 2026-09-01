from __future__ import annotations

import ast
from pathlib import Path


RUNTIME_PATH = Path("ClipAI/app/runtime_entry_panel.py")


def _class_method(name: str) -> ast.FunctionDef:
    tree = ast.parse(RUNTIME_PATH.read_text(encoding="utf-8"))
    runtime_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EntryPanelRuntimeModule"
    )
    return next(
        node
        for node in runtime_class.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_action_selection_cannot_recapture_external_input_or_foreground() -> None:
    selection = _class_method("select_action")
    referenced_attributes = {
        node.attr
        for node in ast.walk(selection)
        if isinstance(node, ast.Attribute)
    }

    assert referenced_attributes.isdisjoint({
        "prepare_entry_input",
        "capture_selection",
        "read_text",
        "read_image",
        "activate",
        "confirm",
        "external_source_reader",
        "workflow_context_reader",
    })


def test_removed_action_time_selection_contracts_do_not_return() -> None:
    production_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("ClipAI").rglob("*.py")
    )

    assert "EntryPanelSelectionId" not in production_source
    assert "EntryPanelInputPrepared" not in production_source


def test_entry_panel_view_does_not_cross_semantic_or_actuation_boundaries() -> None:
    source = Path("ClipAI/ui/unified_entry_panel.py").read_text(encoding="utf-8")
    forbidden = (
        "PopupControl",
        "ActionExecutor",
        "InputResolver",
        "ClipboardTransactionCoordinator",
        "WorkflowRuntimeModule",
        "prepare_entry_input(",
        "start_action(",
    )

    assert [value for value in forbidden if value in source] == []
