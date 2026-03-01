from __future__ import annotations

import pytest

from ClipAI.core.cancellation import CancellationController, LLMCancelledError


def test_cancellation_token_and_controller() -> None:
    ctrl = CancellationController()
    token = ctrl.token
    assert token.is_cancelled() is False

    ctrl.cancel("unit test")
    assert token.is_cancelled() is True
    assert ctrl.reason == "unit test"

    with pytest.raises(LLMCancelledError):
        token.throw_if_cancelled()
