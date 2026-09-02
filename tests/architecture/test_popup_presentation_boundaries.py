from __future__ import annotations

import ast
from pathlib import Path


PROJECTOR = Path(__file__).parents[2] / "ClipAI" / "core" / "popup_presentation.py"


def test_popup_projector_is_core_only_and_tk_free() -> None:
    tree = ast.parse(PROJECTOR.read_text(encoding="utf-8"), filename=str(PROJECTOR))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)

    forbidden = {
        "tkinter",
        "customtkinter",
        "ClipAI.app",
        "ClipAI.platform",
        "ClipAI.providers",
        "ClipAI.services",
        "ClipAI.ui",
    }
    assert not any(
        module == owner or module.startswith(f"{owner}.")
        for module in imported_modules
        for owner in forbidden
    )
