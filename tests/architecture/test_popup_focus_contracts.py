from __future__ import annotations

import ast
from pathlib import Path


def test_focus_entered_requires_named_native_and_toolkit_evidence() -> None:
    violations: list[str] = []
    for root in (Path("ClipAI"), Path("tests")):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "FocusEntered":
                    continue
                keywords = {keyword.arg for keyword in node.keywords}
                if node.args or keywords != {"native_foreground", "toolkit_focused"}:
                    violations.append(f"{path}:{node.lineno}: FocusEntered must name both evidence axes")
    assert violations == [], "\n".join(violations)


def test_only_popup_transition_owner_constructs_focus_projection() -> None:
    violations: list[str] = []
    owner = Path("ClipAI/ui/popup_external_output.py")
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
