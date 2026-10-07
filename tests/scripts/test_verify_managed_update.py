from pathlib import Path
import subprocess
import sys

import pytest

from scripts import verify_managed_update as verifier


@pytest.mark.parametrize("stage, expected", [
    ("fast", []),
    ("synthetic", []),
    ("loopback-http", ["tests/e2e/test_managed_update_loopback_http.py"]),
    ("managed-bundle", ["tests/e2e/test_managed_update_loopback_http.py", "tests/e2e/test_managed_update_bundle.py"]),
])
def test_stages_run_unit_once_then_only_required_integrations(monkeypatch, stage, expected):
    calls = []
    monkeypatch.setattr(verifier, "_run", lambda arguments: calls.append(arguments) or 0)

    assert verifier.main(["--python", sys.executable, "--stage", stage]) == 0

    runner = [str(Path(sys.executable).resolve()), str(verifier.ROOT / "scripts/run_unit_tests.py")]
    assert calls == [runner, *[
        [*runner, "--", path, "-m", "integration", "-q"] for path in expected
    ]]


@pytest.mark.parametrize("failed_stage", [0, 1, 2])
def test_failed_gate_propagates_exit_code_and_never_starts_later_work(monkeypatch, failed_stage):
    calls = []
    def run(arguments):
        calls.append(arguments)
        return 7 if len(calls) == failed_stage + 1 else 0
    monkeypatch.setattr(verifier, "_run", run)

    assert verifier.main(["--python", sys.executable, "--stage", "managed-bundle"]) == 7
    assert len(calls) == failed_stage + 1


def test_synthetic_e2e_is_selected_by_default_unit_marker():
    # Removal of the second run is safe only while default pytest selection
    # collects the synthetic journey. Exit 5 would mean it was deselected.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/e2e/test_managed_update_synthetic.py",
         "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=verifier.ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
