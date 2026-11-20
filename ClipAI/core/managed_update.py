from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import NewType

try:
    from enum import StrEnum as _StrEnum
except ImportError:  # Python 3.10 compatibility
    from enum import Enum

    class _StrEnum(str, Enum):
        __str__ = str.__str__


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


class FailureCode(_StrEnum):
    IDENTITY_INELIGIBLE = "identity_ineligible"
    UPDATE_BUSY = "update_busy"
    UPDATE_INTERRUPTED = "update_interrupted"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    CATALOG_INVALID = "catalog_invalid"
    DOWNLOAD_FAILED = "download_failed"
    SIGNATURE_INVALID = "signature_invalid"
    BUNDLE_INVALID = "bundle_invalid"
    PREPARE_FAILED = "prepare_failed"
    HANDOFF_FAILED = "handoff_failed"
    HANDOFF_TIMEOUT = "handoff_timeout"
    SHUTDOWN_FAILED = "shutdown_failed"
    COMMIT_FAILED = "commit_failed"
    LAUNCH_FAILED = "launch_failed"
    HEALTH_FAILED = "health_failed"
    HEALTH_TIMEOUT = "health_timeout"
    ROLLBACK_FAILED = "rollback_failed"
    INTERNAL_ERROR = "internal_error"


class ManagedUpdateFailure(RuntimeError):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class TransactionPhase(_StrEnum):
    VERIFY = "verify"
    PREPARE = "prepare"
    SHUTDOWN = "shutdown"
    COMMIT = "commit"
    LAUNCH = "launch"
    HEALTH = "health"
    ROLLBACK = "rollback"
    FINALIZE = "finalize"


@dataclass(frozen=True)
class TransactionSnapshot:
    transaction_id: TransactionId
    phase: TransactionPhase
    installed_version: str
    target_version: str
    failure_code: FailureCode | None = None


@dataclass(frozen=True)
class CommitReceipt:
    previous_root: Path
    candidate_root: Path
