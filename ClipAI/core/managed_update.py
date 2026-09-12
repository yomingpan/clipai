from __future__ import annotations

from enum import StrEnum
import re
from typing import NewType


TransactionId = NewType("TransactionId", str)
LaunchAttemptId = NewType("LaunchAttemptId", str)

_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def transaction_id(value: str) -> TransactionId:
    if _IDENTITY.fullmatch(value) is None:
        raise ValueError("transaction id is invalid")
    return TransactionId(value)


def launch_attempt_id(value: str) -> LaunchAttemptId:
    if _IDENTITY.fullmatch(value) is None:
        raise ValueError("launch attempt id is invalid")
    return LaunchAttemptId(value)


class FailureCode(StrEnum):
    IDENTITY_INELIGIBLE = "identity_ineligible"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    CATALOG_INVALID = "catalog_invalid"
    DOWNLOAD_FAILED = "download_failed"
    SIGNATURE_INVALID = "signature_invalid"
    BUNDLE_INVALID = "bundle_invalid"
    PREPARE_FAILED = "prepare_failed"
    SHUTDOWN_FAILED = "shutdown_failed"
    COMMIT_FAILED = "commit_failed"
    LAUNCH_FAILED = "launch_failed"
    HEALTH_FAILED = "health_failed"
    HEALTH_TIMEOUT = "health_timeout"
    ROLLBACK_FAILED = "rollback_failed"
    INTERNAL_ERROR = "internal_error"
