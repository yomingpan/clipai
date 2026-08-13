from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PASTE_PRODUCTION_FILES = (
    ROOT / "ClipAI" / "platform" / "keyboard.py",
    ROOT / "ClipAI" / "services" / "clipboard_transaction.py",
    ROOT / "ClipAI" / "services" / "paste_operation.py",
    ROOT / "ClipAI" / "app" / "runtime_outputs.py",
)
EXPECTED_REASONS = {
    "no_target_observed",
    "target_gone",
    "target_refused_focus",
    "target_focus_timeout",
    "target_changed",
    "modifiers_held",
    "another_paste_active",
    "clipboard_unavailable",
    "unknown",
}


def test_every_paste_failure_reason_is_created_at_a_detection_boundary() -> None:
    constructed: set[str] = set()
    for path in PASTE_PRODUCTION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "PasteFailure" or not node.args:
                continue
            reason = node.args[0]
            if isinstance(reason, ast.Constant) and isinstance(reason.value, str):
                constructed.add(reason.value)

    assert constructed == EXPECTED_REASONS, (
        "Each PasteFailureReason must be constructed where its condition is detected; "
        f"expected {EXPECTED_REASONS}, found {constructed}."
    )


def test_paste_failure_policy_does_not_recover_reason_from_error_messages() -> None:
    violations: list[str] = []
    for path in PASTE_PRODUCTION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and any(
                isinstance(part, ast.Constant) and isinstance(part.value, str)
                for part in (node.left, *node.comparators)
            ):
                rendered = ast.unparse(node)
                if "message" in rendered or "str(error)" in rendered or "str(exc)" in rendered:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {rendered}")

    assert violations == [], (
        "Paste failure reasons are typed at detection time; do not compare message text:\n"
        + "\n".join(violations)
    )


def test_durable_copy_uses_the_container_clipboard_transaction_owner() -> None:
    source = (ROOT / "ClipAI" / "app" / "container.py").read_text(encoding="utf-8")

    assert "OutputActions(\n        clipboard=clipboard_transactions," in source, (
        "OutputActions must serialize durable writes through the one container-scoped "
        "ClipboardTransactionCoordinator."
    )


def test_paste_completion_state_does_not_claim_success() -> None:
    models = (ROOT / "ClipAI" / "core" / "models.py").read_text(encoding="utf-8")
    assignment = models.split("PasteCompletionState = ", 1)[1].split("\n", 1)[0]

    assert "succeeded" not in assignment
