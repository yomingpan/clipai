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
