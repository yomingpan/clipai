from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ClipAI.core.managed_update import CommitReceipt, LaunchAttemptId, TransactionId, TransactionSnapshot
from ClipAI.core.update_artifacts import LaunchReceiptArtifact, StartupHealthArtifact, UpdateRequestArtifact
from ClipAI.core.update_catalog import ManagedUpdateRelease


@dataclass(frozen=True)
class CandidateBuildRequest:
    transaction_id: TransactionId
    candidate_root: Path
    base_python: Path
    expected_version: str
    entrypoint: str


@dataclass(frozen=True)
class CandidateEnvironment:
    root: Path
    python: Path
    entrypoint: Path
    version: str


class CandidateEnvironmentBuilder(Protocol):
    def build(self, request: CandidateBuildRequest) -> CandidateEnvironment: ...


class ManagedUpdateLease(Protocol):
    def close(self) -> None: ...


class ManagedUpdateGate(Protocol):
    def acquire(self) -> ManagedUpdateLease | None: ...


class ManagedReleaseSource(Protocol):
    def discover(
        self,
        *,
        installed_version: str,
        launcher_version: str,
    ) -> ManagedUpdateRelease | None: ...

    def download(
        self,
        release: ManagedUpdateRelease,
        *,
        shared_root: Path,
        transaction_id: TransactionId,
    ) -> Path: ...


class ManagedApplicationLifecycle(Protocol):
    def request_shutdown(self, transaction_id: TransactionId) -> None: ...

    def launch(self, *, version_root: Path, transaction_id: TransactionId, launch_attempt_id: LaunchAttemptId, expected_version: str) -> LaunchReceiptArtifact: ...

    def await_health(self, launch: LaunchReceiptArtifact, *, timeout_sec: float) -> StartupHealthArtifact: ...


class ManagedUpdateBackend(Protocol):
    def verify(self, request: UpdateRequestArtifact) -> None: ...

    def prepare(self, request: UpdateRequestArtifact) -> CandidateEnvironment: ...

    def known_good_root(self, request: UpdateRequestArtifact) -> Path: ...

    def commit(self, candidate: CandidateEnvironment) -> CommitReceipt: ...

    def rollback(self, receipt: CommitReceipt) -> None: ...

    def finalize(self, receipt: CommitReceipt) -> None: ...


class UpdateTransactionJournal(Protocol):
    def record(self, snapshot: TransactionSnapshot) -> None: ...
