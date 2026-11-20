"""Single verification entry point for ClipAI managed-update slices."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("fast", "synthetic", "loopback-http", "managed-bundle")
INTEGRATION_TESTS = {
    "loopback-http": "tests/e2e/test_managed_update_loopback_http.py",
    "managed-bundle": "tests/e2e/test_managed_update_bundle.py",
}


def _run(arguments: list[str]) -> int:
    return subprocess.run(arguments, cwd=ROOT, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=ROOT / ".venv" / "Scripts" / "python.exe")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="fast",
    )
    args = parser.parse_args(argv)
    python = args.python.resolve()
    if not python.is_file():
        parser.error(f"Python environment is unavailable: {python}")
    runner = [str(python), str(ROOT / "scripts" / "run_unit_tests.py")]
    # The complete unit suite already includes the synthetic E2E. Keep each
    # later stage separate so a failed loopback never starts bundle work.
    result = _run(runner)
    if result:
        return result
    for stage in STAGES[2:STAGES.index(args.stage) + 1]:
        result = _run([*runner, "--", INTEGRATION_TESTS[stage], "-m", "integration", "-q"])
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
