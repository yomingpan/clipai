from __future__ import annotations

import ast
from pathlib import Path


def _imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def test_services_do_not_import_ui() -> None:
    base = Path("clipai/services")
    for path in base.glob("*.py"):
        imports = _imports_for(path)
        assert all(not name.startswith("clipai.ui") for name in imports), f"forbidden import in {path}"


def test_providers_do_not_import_ui_or_event_bus_or_clipboard_or_tray() -> None:
    forbidden = ("clipai.ui", "clipai.core.event_bus", "clipai.platform.clipboard", "clipai.platform.tray")
    base = Path("clipai/providers")
    for path in base.glob("*.py"):
        imports = _imports_for(path)
        assert all(not name.startswith(forbidden) for name in imports), f"forbidden import in {path}"
