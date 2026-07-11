"""Testable Windows source-checkout bootstrap for ClipAI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


MIN_PYTHON = (3, 10)
MAX_PYTHON_EXCLUSIVE = (3, 14)
RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class BootstrapError(RuntimeError):
    """An actionable source-install or startup failure."""


def supported_python(version: tuple[int, int]) -> bool:
    return MIN_PYTHON <= version < MAX_PYTHON_EXCLUSIVE


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True)


def venv_python(project_root: Path) -> Path | None:
    for directory in (".venv", "venv"):
        candidate = project_root / directory / "Scripts" / "python.exe"
        if candidate.is_file():
            return candidate
    return None


def run_checked(runner: RunCommand, command: Sequence[str], purpose: str) -> None:
    result = runner(command)
    if result.returncode:
        raise BootstrapError(f"{purpose} failed with exit code {result.returncode}.")


def create_environment(project_root: Path, interpreter: Path, runner: RunCommand) -> Path:
    constraints = project_root / "constraints" / "windows.txt"
    if not constraints.is_file():
        raise BootstrapError(f"Dependency constraints are missing: {constraints}")

    environment = project_root / ".venv"
    run_checked(runner, [str(interpreter), "-m", "venv", str(environment)], "Virtual environment creation")
    python = environment / "Scripts" / "python.exe"
    run_checked(runner, [str(python), "-m", "pip", "install", "--upgrade", "pip"], "pip upgrade")
    run_checked(
        runner,
        [str(python), "-m", "pip", "install", "-c", str(constraints), "-e", str(project_root)],
        "ClipAI installation",
    )
    return python


def prepare(
    project_root: Path,
    interpreter: Path,
    runner: RunCommand = default_runner,
    confirm: Callable[[str], str] = input,
) -> Path:
    existing = venv_python(project_root)
    if existing is not None:
        return existing
    answer = confirm("Virtual environment not found. Create it and install ClipAI? (y/n): ")
    if answer.strip().lower() != "y":
        raise BootstrapError("A virtual environment is required to start ClipAI.")
    return create_environment(project_root, interpreter, runner)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-launch", action="store_true", help="Prepare the environment without starting ClipAI.")
    args = parser.parse_args(argv)
    project_root = args.project_root.resolve()

    if not supported_python(sys.version_info[:2]):
        print("[error] ClipAI requires Python 3.10 through 3.13.", file=sys.stderr)
        return 1
    try:
        python = prepare(project_root, Path(sys.executable))
        if not args.no_launch:
            run_checked(default_runner, [str(python), str(project_root / "main.py")], "ClipAI startup")
    except BootstrapError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
