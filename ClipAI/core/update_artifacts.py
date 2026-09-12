from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from ClipAI.core.managed_update import FailureCode, LaunchAttemptId, TransactionId


@dataclass(frozen=True)
class UpdateRequestArtifact:
    transaction_id: TransactionId
    created_at: str
    installed_version: str
    target_version: str
    installed_executable: Path
    bundle_path: Path
    bundle_size: int
    bundle_sha256: str
    manifest_sha256: str
    key_id: str
    install_root: Path
    shared_root: Path
    managed_install_id: str


@dataclass(frozen=True)
class HandoffReadyArtifact:
    transaction_id: TransactionId
    created_at: str
    candidate_root: Path
    candidate_python: Path
    manifest_sha256: str
    expected_version: str


@dataclass(frozen=True)
class LaunchReceiptArtifact:
    transaction_id: TransactionId
    created_at: str
    launch_attempt_id: LaunchAttemptId
    expected_version: str
    executable_path: Path
    process_id: int


@dataclass(frozen=True)
class StartupHealthArtifact:
    transaction_id: TransactionId
    created_at: str
    launch_attempt_id: LaunchAttemptId
    expected_version: str
    actual_version: str
    executable_path: Path
    healthy: bool


UpdateOutcome: TypeAlias = Literal["updated", "rolled_back", "failed"]


@dataclass(frozen=True)
class UpdateResultArtifact:
    transaction_id: TransactionId
    created_at: str
    outcome: UpdateOutcome
    active_version: str
    failure_code: FailureCode | None = None
    rollback_failure_code: FailureCode | None = None


UpdateArtifact: TypeAlias = (
    UpdateRequestArtifact
    | HandoffReadyArtifact
    | LaunchReceiptArtifact
    | StartupHealthArtifact
    | UpdateResultArtifact
)


def validate_health_relation(
    launch: LaunchReceiptArtifact,
    health: StartupHealthArtifact,
) -> None:
    if (
        launch.transaction_id != health.transaction_id
        or launch.launch_attempt_id != health.launch_attempt_id
        or launch.expected_version != health.expected_version
        or health.actual_version != launch.expected_version
        or launch.executable_path.resolve() != health.executable_path.resolve()
        or not health.healthy
    ):
        raise ValueError("startup health does not match launch")
