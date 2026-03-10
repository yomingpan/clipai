from __future__ import annotations

import pytest

from clipai.core.llm_provider import LLMAuthError, LLMRateLimitError, LLMResponseError, map_http_error


def test_map_http_error_auth() -> None:
    err = map_http_error(401, "nope")
    assert isinstance(err, LLMAuthError)


def test_map_http_error_rate_limit() -> None:
    err = map_http_error(429, "slow down", retry_after=2.5)
    assert isinstance(err, LLMRateLimitError)
    assert err.retry_after == 2.5


def test_map_http_error_response() -> None:
    err = map_http_error(400, "bad")
    assert isinstance(err, LLMResponseError)
