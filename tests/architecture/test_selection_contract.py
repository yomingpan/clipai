from pathlib import Path
import ast


def test_selection_reader_cannot_erase_capture_status():
    ports = ast.parse(Path("ClipAI/core/ports.py").read_text(encoding="utf-8"))
    reader = next(node for node in ports.body if isinstance(node, ast.ClassDef) and node.name == "SelectionReader")
    methods = {node.name for node in reader.body if isinstance(node, ast.FunctionDef)}
    assert methods == {"capture", "begin_capture"}


def test_production_assembly_wires_native_probe_and_sole_clipboard_owner():
    source = Path("ClipAI/app/container.py").read_text(encoding="utf-8")
    assert source.count("ClipboardTransactionCoordinator(clipboard)") == 1
    assert "selection_probe = WindowsSelectionProbe()" in source
    assert "background_components=(selection_probe,)" in source


def test_uia_worker_has_no_clipboard_or_keyboard_side_effects():
    source = Path("ClipAI/platform/selection_uia_worker.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "ClipAI.platform.clipboard" not in modules
    assert "pynput.keyboard" not in modules
    assert "GetText(-1)" in source


def test_application_specific_selection_identity_stays_in_profile_module():
    for path in (
        "ClipAI/platform/selection_uia_worker.py",
        "ClipAI/services/selection_capture.py",
        "ClipAI/app/runtime.py",
    ):
        source = Path(path).read_text(encoding="utf-8").casefold()
        assert "anki" not in source
        assert "mainwebview" not in source
