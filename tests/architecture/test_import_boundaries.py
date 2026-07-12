from __future__ import annotations

import ast
from pathlib import Path


ALLOWED = {
    "core": {"core"},
    "services": {"core", "services"},
    "platform": {"core", "platform"},
    "providers": {"core", "providers"},
    "ui": {"core", "ui"},
    "support": {"support"},
}


def test_layer_import_boundaries() -> None:
    violations: list[str] = []
    package = Path("ClipAI")
    for layer, allowed in ALLOWED.items():
        root = package / layer
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module or not node.module.startswith("ClipAI."):
                    continue
                imported_layer = node.module.split(".")[1]
                if imported_layer not in allowed:
                    violations.append(f"{path}: {layer} imports {node.module}")
    assert violations == []


def test_no_global_event_bus_or_legacy_modules() -> None:
    files = [path for path in Path("ClipAI").rglob("*.py")]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "get_event_bus" not in source
    assert "class EventBus" not in source
    assert not Path("ClipAI/core/event_bus.py").exists()
    assert not Path("ClipAI/services/vertical_slice.py").exists()
    assert not Path("ClipAI/providers/factory.py").exists()


def test_only_composition_root_reads_environment_secrets() -> None:
    violations = []
    for path in Path("ClipAI").rglob("*.py"):
        if path == Path("ClipAI/app/container.py"):
            continue
        source = path.read_text(encoding="utf-8")
        if "os.getenv(" in source or "os.environ" in source:
            violations.append(str(path))
    assert violations == []


def test_tracked_sources_do_not_contain_merge_conflict_markers() -> None:
    markers = ("<<<<<<< ", "=======", ">>>>>>> ")
    violations: list[str] = []
    roots = (Path("ClipAI"), Path("tests"), Path("config"), Path("docs"), Path(".github"))
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".yaml", ".yml", ".md"}:
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if any(line.startswith(marker) for marker in markers):
                    violations.append(f"{path}:{line_number}")
    assert violations == []


def test_runtime_does_not_probe_optional_capabilities() -> None:
    source = Path("ClipAI/app/runtime.py").read_text(encoding="utf-8")
    assert "hasattr(" not in source
    assert "getattr(" not in source
