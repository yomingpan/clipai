from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_matches_the_supported_runtime() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "clipai"' in pyproject
    assert 'version = "3.0.1"' in pyproject
    assert 'requires-python = ">=3.10"' in pyproject
    assert '"pip-system-certs>=5; sys_platform == \'win32\'"' in pyproject
    assert '"certifi-win32"' not in pyproject


def test_windows_launcher_checks_the_minimum_python_version() -> None:
    launcher = (PROJECT_ROOT / "run_clipai.bat").read_text(encoding="utf-8")

    assert 'call :require_python_310 "!PYTHON_EXE!"' in launcher
    assert '"!PYTHON_EXE!" -m venv .venv' in launcher
    assert "ClipAI requires Python 3.10 or newer." in launcher
