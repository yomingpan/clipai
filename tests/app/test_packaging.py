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

    assert "scripts\\bootstrap_windows.ps1" in launcher
    assert "pip install" not in launcher
    assert "-m venv" not in launcher


def test_windows_bootstrap_installs_and_selects_python_312() -> None:
    bootstrap_script = (PROJECT_ROOT / "scripts" / "bootstrap_windows.ps1").read_text(encoding="utf-8")

    assert '$RequiredPython = "3.12"' in bootstrap_script
    assert '$PythonManagerPackage = "9NQ7512CXL7T"' in bootstrap_script
    assert "-V:3.12" in bootstrap_script
    assert "--accept-package-agreements" in bootstrap_script
    assert "scripts\\bootstrap.py" in bootstrap_script


@pytest.mark.parametrize(
    ("version", "expected"),
    [((3, 11), False), ((3, 12), True), ((3, 13), False), ((3, 14), False)],
)
def test_supported_python_range(version: tuple[int, int], expected: bool) -> None:
    assert bootstrap.supported_python(version) is expected


def write_install_inputs(project_root: Path) -> None:
    (project_root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    constraints = project_root / "constraints" / "windows.txt"
    constraints.parent.mkdir(exist_ok=True)
    constraints.write_text("httpx==0.28.1\n", encoding="utf-8")


def test_prepare_reuses_a_ready_python_312_environment(tmp_path: Path) -> None:
    write_install_inputs(tmp_path)
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    bootstrap.mark_environment_ready(tmp_path, python)

    assert bootstrap.prepare(
        tmp_path,
        Path("system-python"),
        confirm=lambda _: "n",
        read_version=lambda _: (3, 12),
    ) == python


def test_prepare_declines_environment_creation(tmp_path: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError, match="required"):
        bootstrap.prepare(tmp_path, Path("python"), confirm=lambda _: "n")


def test_prepare_refreshes_dependencies_when_inputs_change(tmp_path: Path) -> None:
    write_install_inputs(tmp_path)
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[1:3] == ["-m", "venv"]:
            created_python = Path(command[-1]) / "Scripts" / "python.exe"
            created_python.parent.mkdir(parents=True)
            created_python.touch()
        return subprocess.CompletedProcess(command, 0)

    result = bootstrap.prepare(
        tmp_path,
        Path("system-python"),
        runner=runner,
        read_version=lambda _: (3, 12),
        assume_yes=True,
    )

    assert result == python
    assert len(commands) == 2
    assert bootstrap.environment_is_ready(tmp_path, python)


def test_prepare_preserves_an_incompatible_dot_venv(tmp_path: Path) -> None:
    write_install_inputs(tmp_path)
    old_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    old_python.parent.mkdir(parents=True)
    old_python.touch()
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[1:3] == ["-m", "venv"]:
            created_python = Path(command[-1]) / "Scripts" / "python.exe"
            created_python.parent.mkdir(parents=True)
            created_python.touch()
        return subprocess.CompletedProcess(command, 0)

    python = bootstrap.prepare(
        tmp_path,
        Path("python312"),
        runner=runner,
        read_version=lambda _: (3, 13),
        assume_yes=True,
    )

    assert (tmp_path / ".venv.incompatible" / "Scripts" / "python.exe").is_file()
    assert python == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert commands[0][0] == "python312"


def test_create_environment_uses_runtime_constraints(tmp_path: Path) -> None:
    write_install_inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[1:3] == ["-m", "venv"]:
            created_python = Path(command[-1]) / "Scripts" / "python.exe"
            created_python.parent.mkdir(parents=True)
            created_python.touch()
        return subprocess.CompletedProcess(command, 0)

    python = bootstrap.create_environment(tmp_path, Path("python"), runner)

    assert python == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert commands[0][1:3] == ["-m", "venv"]
    assert "--upgrade" in commands[1]
    assert "-c" in commands[2]
    assert ".[dev]" not in commands[2]
    assert bootstrap.environment_is_ready(tmp_path, python)


def test_dependency_refresh_avoids_pip_and_system_truststore_double_patch(tmp_path: Path) -> None:
    write_install_inputs(tmp_path)
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0)

    bootstrap.install_project(tmp_path, python, runner)

    pip_commands = [command for command in commands if command[1:3] == ["-m", "pip"]]
    assert len(pip_commands) == 2
    assert all("--use-deprecated=legacy-certs" in command for command in pip_commands)


def test_default_runner_exports_legacy_certificate_mode_to_pip_children(monkeypatch: pytest.MonkeyPatch) -> None:
    received: dict[str, object] = {}

    def fake_run(command, **kwargs):
        received["command"] = command
        received.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    bootstrap.default_runner(["python", "-m", "pip", "install"])

    assert received["env"] is not None
    assert received["env"]["PIP_USE_DEPRECATED"] == "legacy-certs"


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
        if command[1:3] == ["-m", "venv"]:
            created_python = Path(command[-1]) / "Scripts" / "python.exe"
            created_python.parent.mkdir(parents=True)
            created_python.touch()
        return subprocess.CompletedProcess(command, 7 if calls == 3 else 0)

    with pytest.raises(bootstrap.BootstrapError, match="ClipAI installation failed with exit code 7"):
        bootstrap.create_environment(tmp_path, Path("python"), runner)


def test_release_workflow_parses_toml_on_python_310() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "pip build tomli" in workflow
    assert "import tomli" in workflow
    assert "import tomllib" not in workflow
