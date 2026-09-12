"""Single verification entry point for ClipAI managed-update slices."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run(arguments: list[str]) -> int:
    return subprocess.run(arguments, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=ROOT / ".venv" / "Scripts" / "python.exe")
    parser.add_argument(
        "--stage",
        choices=("fast", "synthetic", "loopback-http", "managed-bundle"),
        default="fast",
    )
    args = parser.parse_args()
    python = args.python.resolve()
    if not python.is_file():
        parser.error(f"Python environment is unavailable: {python}")
    if args.stage != "fast":
        print(f"[error] managed-update stage is not implemented yet: {args.stage}", file=sys.stderr)
        return 2
    return _run([str(python), str(ROOT / "scripts" / "run_unit_tests.py")])


if __name__ == "__main__":
    raise SystemExit(main())
