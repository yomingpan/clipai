"""Regenerate Windows runtime constraints in a clean Python 3.10 environment."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(command, check=True, text=True, capture_output=capture)
    return result.stdout if capture else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python 3.10 interpreter used to resolve dependencies.")
    parser.add_argument("--output", type=Path, default=Path("constraints/windows.txt"))
    args = parser.parse_args()

    version = subprocess.run(
        [args.python, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if version != "3.10":
        raise SystemExit(f"constraints must be generated with Python 3.10, found {version}")

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="clipai-constraints-") as temporary:
        python = Path(temporary) / "Scripts" / "python.exe"
        run([args.python, "-m", "venv", temporary])
        run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(python), "-m", "pip", "install", str(root)])
        frozen = run([str(python), "-m", "pip", "freeze", "--exclude-editable"], capture=True)

    lines = sorted(
        line for line in frozen.splitlines() if line and not line.lower().startswith("clipai==")
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "# Generated on Windows with Python 3.10.\n"
        "# Update with: python scripts/update_windows_constraints.py\n"
        + "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
