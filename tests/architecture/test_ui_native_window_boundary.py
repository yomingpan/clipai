from __future__ import annotations

import ast
from pathlib import Path


def test_ui_does_not_branch_on_platform_or_reach_windll() -> None:
    violations: list[str] = []
    for path in Path("ClipAI/ui").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "platform"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sys"
            ):
                violations.append(f"{path}:{node.lineno}: UI branches on sys.platform")
            if isinstance(node, ast.Attribute) and node.attr == "windll":
                violations.append(f"{path}:{node.lineno}: UI reaches ctypes.windll")

    assert violations == [], "UI must consume injected native-window facts:\n" + "\n".join(violations)
