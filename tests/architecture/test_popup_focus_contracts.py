from __future__ import annotations

import ast
from pathlib import Path


def test_popup_control_state_is_private_to_popup_control() -> None:
    violations: list[str] = []
    owner = Path("ClipAI/ui/popup_control.py")
    for path in Path("ClipAI").rglob("*.py"):
        if path == owner or path.name == "_popup_control_state.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any("_popup_control_state" in module for module in modules):
                violations.append(f"{path}:{node.lineno}: Popup control state bypasses PopupControl")
    assert violations == [], "\n".join(violations)


def test_only_popup_transition_owner_constructs_focus_projection() -> None:
    violations: list[str] = []
    owner = Path("ClipAI/ui/_popup_control_state.py")
    for path in Path("ClipAI").rglob("*.py"):
        if path == owner:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "SetFocusProjection":
                violations.append(f"{path}:{node.lineno}: SetFocusProjection bypasses transition owner")
    assert violations == [], "\n".join(violations)


def test_external_visibility_result_is_never_discarded_as_a_bare_expression() -> None:
    violations: list[str] = []
    for path in Path("ClipAI").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            function = node.value.func
            if isinstance(function, ast.Attribute) and function.attr == "apply_external_output_visibility":
                violations.append(f"{path}:{node.lineno}: visibility result is discarded")
    assert violations == [], "\n".join(violations)


def test_voice_admission_does_not_read_widget_visibility_or_split_by_trigger() -> None:
    violations: list[str] = []
    for path in Path("ClipAI").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                path.parts[:2] == ("ClipAI", "app")
                and isinstance(node, ast.Attribute)
                and "follow_up" in node.attr
                and "visible" in node.attr
            ):
                violations.append(f"{path}:{node.lineno}: app reads Follow-up widget visibility")
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and "voice" in node.name
                and ("admit" in node.name or "admission" in node.name)
                and ("shortcut" in node.name or "popup" in node.name)
            ):
                violations.append(f"{path}:{node.lineno}: Voice admission is split by trigger")

    runtime_tree = ast.parse(
        Path("ClipAI/app/runtime_voice_input.py").read_text(encoding="utf-8"),
        filename="ClipAI/app/runtime_voice_input.py",
    )
    popup_capture = next(
        node
        for node in ast.walk(runtime_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_start_popup_capture"
    )
    for node in ast.walk(popup_capture):
        if isinstance(node, ast.Attribute) and node.attr in {"status", "active_invocation_id", "available_actions"}:
            violations.append(
                f"ClipAI/app/runtime_voice_input.py:{node.lineno}: Popup Voice duplicates destination matrix"
            )
    assert violations == [], "\n".join(violations)
