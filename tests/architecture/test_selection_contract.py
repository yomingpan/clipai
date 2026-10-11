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


def test_emitted_selection_reasons_belong_to_core_closed_set():
    from ClipAI.core.models import SelectionReason
    reasons = {reason.value for reason in SelectionReason}
    for name in (
        'platform/selection_uia_worker.py', 'platform/selection_uia.py',
        'services/clipboard_transaction.py', 'services/selection_capture.py',
        'services/input_resolver.py',
    ):
        tree = ast.parse(Path('ClipAI', name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = getattr(node.func, 'id', '')
            values = [kw.value for kw in node.keywords if kw.arg == 'reason'] if function == 'SelectionCaptureOutcome' else []
            if function == '_unknown' and node.args:
                values.append(node.args[0])
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
                    assert value.value in reasons, (name, node.lineno, value.value)


def test_selection_consumers_do_not_compare_reason_strings():
    from ClipAI.core.models import SelectionReason
    values = {reason.value for reason in SelectionReason}
    for directory in ('app', 'ui', 'services'):
        for path in Path('ClipAI', directory).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                if isinstance(node, ast.Compare):
                    literals = [part.value for part in ast.walk(node) if isinstance(part, ast.Constant) and isinstance(part.value, str)]
                    assert not (set(literals) & values), (path, node.lineno)


def test_guidance_services_do_not_duplicate_core_reason_collections():
    for name in ('selection_feedback.py', 'entry_input_preview.py'):
        source = Path('ClipAI/services', name).read_text(encoding='utf-8')
        tree = ast.parse(source)
        assert not any(isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'frozenset' for node in ast.walk(tree))
        assert not any(isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith('uia_') for node in ast.walk(tree))


def test_rendered_content_is_tk_free_and_surface_has_one_content_projection():
    for name in ('presentation_render.py', 'text_layout.py'):
        tree = ast.parse(Path('ClipAI/ui', name).read_text(encoding='utf-8'))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
        assert not any('tkinter' in name for name in imports)
    tree = ast.parse(Path('ClipAI/ui/base_dialog.py').read_text(encoding='utf-8'))
    surface = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'BaseResultSurface')
    attributes = {node.attr for node in ast.walk(surface) if isinstance(node, ast.Attribute)}
    assert '_rendered_content' in attributes
    assert not attributes & {'_canonical_selection_segments', '_selection_block_ranges'}
