from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_follow_up_execution_and_prompt_building_each_have_one_public_pipeline() -> None:
    executor_methods = _class_methods(
        ROOT / "ClipAI" / "services" / "execute_action.py",
        "ActionExecutor",
    )
    prompt_methods = _class_methods(
        ROOT / "ClipAI" / "services" / "prompt_builder.py",
        "PromptBuilder",
    )

    assert {name for name in executor_methods if "follow_up" in name} == {
        "execute_follow_up_invocation",
    }
    assert {name for name in prompt_methods if "follow_up" in name} == {
        "build_follow_up",
    }


def test_runtime_dispatches_both_roots_through_one_continuation_seam() -> None:
    path = ROOT / "ClipAI" / "app" / "runtime_workflows.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    called_attributes = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]

    assert called_attributes.count("execute_follow_up_invocation") == 1
    assert "execute_voice_draft_follow_up_invocation" not in called_attributes
    assert "_start_voice_draft_follow_up" not in called_attributes
    assert "execute_contextual_question_invocation" not in called_attributes


def test_contextual_question_is_not_a_configured_action_or_second_pipeline() -> None:
    actions = (ROOT / "config" / "actions.yaml").read_text(encoding="utf-8")
    runtime = (ROOT / "ClipAI" / "app" / "runtime_workflows.py").read_text(encoding="utf-8")

    assert "id: contextual_question" not in actions
    assert runtime.count("execute_follow_up_invocation") == 1


def test_legacy_voice_only_follow_up_policy_module_is_removed() -> None:
    assert not (ROOT / "ClipAI" / "services" / "voice_draft_follow_up.py").exists()
