from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from ClipAI.core.models import ActionInvocation, LLMRequest


PACK_MODULE_PREFIXES = (
    "ClipAI.services.action_language_packs",
    "ClipAI.app.language_pack",
    "ClipAI.platform.action_language_selection",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    return tuple(imported)


def test_execution_and_device_modules_do_not_import_language_pack_owners() -> None:
    paths = [*Path("ClipAI/providers").rglob("*.py")]
    paths.extend(
        Path(path)
        for path in (
            "ClipAI/services/workflow_controller.py",
            "ClipAI/services/prompt_builder.py",
            "ClipAI/services/voice_input.py",
            "ClipAI/services/speech_coordinator.py",
            "ClipAI/app/provider_execution.py",
            "ClipAI/app/runtime_workflows.py",
            "ClipAI/app/runtime_voice_input.py",
            "ClipAI/app/speech_execution.py",
        )
    )

    violations = [
        f"{path}: {module}"
        for path in paths
        for module in _imports(path)
        if module.startswith(PACK_MODULE_PREFIXES)
    ]

    assert violations == []


def test_ui_cannot_read_language_pack_files_or_concrete_store() -> None:
    forbidden_imports = (
        "yaml",
        "ClipAI.app.config_loader",
        "ClipAI.app.language_pack",
        "ClipAI.platform.action_language_selection",
    )
    forbidden_literals = (
        "language_packs.yaml",
        "manifest.yaml",
        "action_language_pack.json",
    )
    violations: list[str] = []
    for path in Path("ClipAI/ui").rglob("*.py"):
        for module in _imports(path):
            if module.startswith(forbidden_imports):
                violations.append(f"{path}: imports {module}")
        source = path.read_text(encoding="utf-8")
        for literal in forbidden_literals:
            if literal in source:
                violations.append(f"{path}: reads {literal}")

    assert violations == []


def test_execution_intents_do_not_gain_pack_or_locale_decision_fields() -> None:
    request_fields = {field.name for field in fields(LLMRequest)}
    invocation_fields = {field.name for field in fields(ActionInvocation)}
    forbidden = {"locale", "pack_id", "language_pack", "action_language"}

    assert request_fields == {"messages", "model", "temperature"}
    assert invocation_fields.isdisjoint(forbidden)


def test_runtime_execution_does_not_branch_on_pack_identity() -> None:
    paths = [*Path("ClipAI/providers").rglob("*.py")]
    paths.extend(
        Path(path)
        for path in (
            "ClipAI/services/workflow_controller.py",
            "ClipAI/services/prompt_builder.py",
            "ClipAI/app/provider_execution.py",
            "ClipAI/app/runtime_workflows.py",
        )
    )
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Compare, ast.If, ast.IfExp, ast.Match)):
                continue
            expression = ast.unparse(node)
            if "pack_id" in expression or "action_language.identity" in expression:
                violations.append(f"{path}:{node.lineno}")

    assert violations == []
