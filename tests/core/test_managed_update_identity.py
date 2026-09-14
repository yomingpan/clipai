from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from ClipAI.core.managed_update import FailureCode, launch_attempt_id, transaction_id


def test_managed_update_identities_are_explicit_and_validated():
    assert transaction_id("tx-01") == "tx-01"
    assert launch_attempt_id("launch_01") == "launch_01"
    with pytest.raises(ValueError):
        transaction_id("../escape")
    with pytest.raises(ValueError):
        launch_attempt_id("")


def test_failure_codes_are_stable_machine_values():
    assert FailureCode.HEALTH_TIMEOUT == "health_timeout"
    assert FailureCode.ROLLBACK_FAILED == "rollback_failed"
    assert FailureCode.UPDATE_BUSY == "update_busy"


def test_managed_update_contract_loads_without_stdlib_strenum():
    module_path = Path(__file__).resolve().parents[2] / "ClipAI" / "core" / "managed_update.py"
    probe = textwrap.dedent(
        f"""
        import enum
        import importlib.util
        import sys

        del enum.StrEnum
        spec = importlib.util.spec_from_file_location("managed_update_compat_probe", {str(module_path)!r})
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        assert module.FailureCode.HEALTH_TIMEOUT == "health_timeout"
        assert str(module.TransactionPhase.FINALIZE) == "finalize"
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
