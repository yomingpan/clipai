from __future__ import annotations

import ast
from pathlib import Path


NATIVE_MODULES = {"ctypes", "win32api", "win32con", "win32gui", "winreg"}


def test_only_platform_imports_native_windows_modules() -> None:
    violations: list[str] = []
    for path in Path("ClipAI").rglob("*.py"):
        if path.parts[1] == "platform":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: set[str] = set()
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = {node.module.split(".", 1)[0]}
            forbidden = sorted(imported & NATIVE_MODULES)
            if forbidden:
                violations.append(f"{path}:{node.lineno}: imports {', '.join(forbidden)} outside platform/")

    assert violations == [], "Native Windows modules belong behind platform adapters:\n" + "\n".join(violations)
