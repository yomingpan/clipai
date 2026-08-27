"""Run ClipAI's unit and sim tests in an explicitly writable test environment."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


TEST_TEMP_ROOT_ENV = "CLIPAI_TEST_TEMP_ROOT"


class TestEnvironmentError(RuntimeError):
    """The test runner could not create isolated temporary storage."""


@dataclass(frozen=True)
class TestEnvironment:
    base_temp: Path
    cache_dir: Path


def _require_writable(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / ".clipai-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
    finally:
        if probe.exists():
            probe.unlink()


def prepare_test_environment(
    project_root: Path,
    environment: Mapping[str, str] | None = None,
    temporary_directory: Path | None = None,
) -> TestEnvironment:
    """Create pytest storage without relying implicitly on pytest's global default."""
    configured_environment = os.environ if environment is None else environment
    configured_root = configured_environment.get(TEST_TEMP_ROOT_ENV)
    candidates = (
        (Path(configured_root),)
        if configured_root
        else (
            (temporary_directory or Path(tempfile.gettempdir())) / "clipai-tests",
            project_root / ".clipai-test-artifacts",
        )
    )
    failures: list[str] = []

    for root in candidates:
        try:
            _require_writable(root)
            cache_dir = root / "cache"
            _require_writable(cache_dir)
            base_temp = Path(tempfile.mkdtemp(prefix="run-", dir=root))
        except OSError as exc:
            failures.append(f"{root}: {exc}")
            continue
        return TestEnvironment(base_temp=base_temp, cache_dir=cache_dir)

    detail = "; ".join(failures)
    raise TestEnvironmentError(
        "ClipAI unit-test environment is unavailable: no writable temporary directory. "
        f"Set {TEST_TEMP_ROOT_ENV} to a writable directory. Details: {detail}"
    )


def pytest_command(test_environment: TestEnvironment, pytest_arguments: Sequence[str]) -> list[str]:
    """Build the single pytest command used locally and in CI."""
    return [
        sys.executable,
        "-m",
        "pytest",
        "--basetemp",
        str(test_environment.base_temp),
        "-o",
        f"cache_dir={test_environment.cache_dir}",
        *pytest_arguments,
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("pytest_arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    pytest_arguments = args.pytest_arguments
    if pytest_arguments[:1] == ["--"]:
        pytest_arguments = pytest_arguments[1:]

    try:
        test_environment = prepare_test_environment(args.project_root.resolve())
    except TestEnvironmentError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    return subprocess.run(
        pytest_command(test_environment, pytest_arguments),
        cwd=args.project_root,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
