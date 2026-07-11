from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts import bootstrap


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_matches_the_supported_runtime() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "clipai"' in pyproject
    assert 'version = "3.0.1"' in pyproject
    assert 'requires-python = ">=3.10,<3.14"' in pyproject
    assert '"pip-system-certs>=5; sys_platform == \'win32\'"' in pyproject
    assert '"certifi-win32"' not in pyproject

    constraints = (PROJECT_ROOT / "constraints" / "windows.txt").read_text(encoding="utf-8")
    for transitive_dependency in ("aiohttp==", "pythonnet==", "truststore=="):
        assert transitive_dependency in constraints


def test_windows_launcher_is_a_thin_bootstrap_entrypoint() -> None:
    launcher = (PROJECT_ROOT / "run_clipai.bat").read_text(encoding="utf-8")

    assert "scripts\\bootstrap.py" in launcher
    assert "pip install" not in launcher
    assert "-m venv" not in launcher
    assert "ClipAI requires Python 3.10 through 3.13." in launcher


@pytest.mark.parametrize(
    ("version", "expected"),
    [((3, 9), False), ((3, 10), True), ((3, 13), True), ((3, 14), False)],
)
def test_supported_python_range(version: tuple[int, int], expected: bool) -> None:
    assert bootstrap.supported_python(version) is expected


def test_prepare_reuses_an_existing_environment(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()

    assert bootstrap.prepare(tmp_path, Path("system-python"), confirm=lambda _: "n") == python


def test_prepare_declines_environment_creation(tmp_path: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError, match="required"):
        bootstrap.prepare(tmp_path, Path("python"), confirm=lambda _: "n")


def test_create_environment_uses_runtime_constraints(tmp_path: Path) -> None:
    constraints = tmp_path / "constraints" / "windows.txt"
    constraints.parent.mkdir()
    constraints.write_text("requests==2.32.3\n", encoding="utf-8")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0)

    python = bootstrap.create_environment(tmp_path, Path("python"), runner)

    assert python == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert commands[0][1:3] == ["-m", "venv"]
    assert "--upgrade" in commands[1]
    assert "-c" in commands[2]
    assert ".[dev]" not in commands[2]


def test_create_environment_reports_missing_constraints(tmp_path: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError, match="constraints are missing"):
        bootstrap.create_environment(tmp_path, Path("python"), lambda _: subprocess.CompletedProcess([], 0))


def test_failed_install_has_actionable_stage(tmp_path: Path) -> None:
    constraints = tmp_path / "constraints" / "windows.txt"
    constraints.parent.mkdir()
    constraints.touch()
    calls = 0

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 7 if calls == 3 else 0)

    with pytest.raises(bootstrap.BootstrapError, match="ClipAI installation failed with exit code 7"):
        bootstrap.create_environment(tmp_path, Path("python"), runner)


def test_release_workflow_parses_toml_on_python_310() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "pip build tomli" in workflow
    assert "import tomli" in workflow
    assert "import tomllib" not in workflow
