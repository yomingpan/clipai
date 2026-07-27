"""Testable Windows source-checkout bootstrap for ClipAI."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


REQUIRED_PYTHON = (3, 12)
READY_MARKER = ".clipai-bootstrap"
RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
ReadVersion = Callable[[Path], tuple[int, int] | None]


class BootstrapError(RuntimeError):
    """An actionable source-install or startup failure."""


def supported_python(version: tuple[int, int]) -> bool:
    return version == REQUIRED_PYTHON


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True)


def venv_python(project_root: Path) -> Path | None:
    for directory in (".venv", "venv"):
        candidate = project_root / directory / "Scripts" / "python.exe"
        if candidate.is_file():
            return candidate
    return None


def python_version(interpreter: Path) -> tuple[int, int] | None:
    result = subprocess.run(
        [
            str(interpreter),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return None
    try:
        major, minor = result.stdout.strip().split(".")
        return int(major), int(minor)
    except (TypeError, ValueError):
        return None


def install_fingerprint(project_root: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"python=3.12\n")
    for relative_path in (Path("pyproject.toml"), Path("constraints/windows.txt")):
        path = project_root / relative_path
        if not path.is_file():
            raise BootstrapError(f"Installation input is missing: {path}")
        digest.update(relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def environment_is_ready(project_root: Path, python: Path) -> bool:
    marker = python.parents[1] / READY_MARKER
    try:
        return marker.read_text(encoding="utf-8").strip() == install_fingerprint(project_root)
    except OSError:
        return False


def mark_environment_ready(project_root: Path, python: Path) -> None:
    marker = python.parents[1] / READY_MARKER
    marker.write_text(install_fingerprint(project_root) + "\n", encoding="utf-8")


def run_checked(runner: RunCommand, command: Sequence[str], purpose: str) -> None:
    result = runner(command)
    if result.returncode:
        raise BootstrapError(f"{purpose} failed with exit code {result.returncode}.")


def install_project(project_root: Path, python: Path, runner: RunCommand) -> None:
    constraints = project_root / "constraints" / "windows.txt"
    if not constraints.is_file():
        raise BootstrapError(f"Dependency constraints are missing: {constraints}")

    run_checked(runner, [str(python), "-m", "pip", "install", "--upgrade", "pip"], "pip upgrade")
    run_checked(
        runner,
        [str(python), "-m", "pip", "install", "-c", str(constraints), "-e", str(project_root)],
        "ClipAI installation",
    )
    mark_environment_ready(project_root, python)


def create_environment(project_root: Path, interpreter: Path, runner: RunCommand) -> Path:
    constraints = project_root / "constraints" / "windows.txt"
    if not constraints.is_file():
        raise BootstrapError(f"Dependency constraints are missing: {constraints}")
    environment = project_root / ".venv"
    run_checked(runner, [str(interpreter), "-m", "venv", str(environment)], "Virtual environment creation")
    python = environment / "Scripts" / "python.exe"
    if not python.is_file():
        raise BootstrapError(f"Virtual environment creation did not produce {python}.")
    install_project(project_root, python, runner)
    return python


def retire_incompatible_environment(project_root: Path) -> Path:
    environment = project_root / ".venv"
    backup = project_root / ".venv.incompatible"
    suffix = 2
    while backup.exists():
        backup = project_root / f".venv.incompatible-{suffix}"
        suffix += 1
    environment.replace(backup)
    return backup


def prepare(
    project_root: Path,
    interpreter: Path,
    runner: RunCommand = default_runner,
    confirm: Callable[[str], str] = input,
    read_version: ReadVersion = python_version,
    assume_yes: bool = False,
) -> Path:
    existing = venv_python(project_root)
    if existing is not None:
        if supported_python(read_version(existing) or (0, 0)):
            if not environment_is_ready(project_root, existing):
                print("[clipai] Installing or refreshing dependencies...", flush=True)
                install_project(project_root, existing, runner)
            return existing
        if existing.parent.parent.name == ".venv":
            backup = retire_incompatible_environment(project_root)
            print(f"[clipai] Preserved incompatible environment as {backup.name}.", flush=True)

    if not assume_yes:
        answer = confirm("Python 3.12 environment not found. Create it and install ClipAI? (y/n): ")
    else:
        answer = "y"
    if answer.strip().lower() != "y":
        raise BootstrapError("A virtual environment is required to start ClipAI.")
    print("[clipai] Creating Python 3.12 virtual environment...", flush=True)
    return create_environment(project_root, interpreter, runner)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-launch", action="store_true", help="Prepare the environment without starting ClipAI.")
    parser.add_argument("--yes", action="store_true", help="Create or repair the environment without prompting.")
    args = parser.parse_args(argv)
    project_root = args.project_root.resolve()

    if not supported_python(sys.version_info[:2]):
        print("[error] ClipAI bootstrap requires Python 3.12.", file=sys.stderr)
        return 1
    try:
        python = prepare(project_root, Path(sys.executable), assume_yes=args.yes)
        if not args.no_launch:
            run_checked(default_runner, [str(python), str(project_root / "main.py")], "ClipAI startup")
    except BootstrapError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
