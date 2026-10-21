import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_inline_has_one_pill_and_no_legacy_choice_window():
    assert not (ROOT / "ClipAI/ui/inline_dictation.py").exists()
    owner = (ROOT / "ClipAI/ui/inline_dictation_owner.py").read_text(encoding="utf-8")
    assert "InlinePill" in owner
    assert "VoiceProjection" not in owner


def test_pill_and_popup_voice_shapes_and_palette_come_from_shared_visuals():
    for path, class_name, draw_method in (
        ("ClipAI/ui/inline_pill.py", "InlinePill", "draw_pill"),
        ("ClipAI/ui/base_dialog.py", "_VoiceWaveIndicator", "draw_voice_capsule"),
    ):
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        assert any(isinstance(node, ast.ImportFrom) and node.module == "ClipAI.ui" and any(alias.name == "voice_visuals" for alias in node.names) for node in tree.body)
        widget = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
        assert not any(isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("#") for node in ast.walk(widget))
        assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == draw_method for node in ast.walk(widget))
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"create_polygon", "create_line", "create_oval"} for node in ast.walk(widget))
