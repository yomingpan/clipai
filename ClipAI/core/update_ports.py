from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ClipAI.core.managed_update import TransactionId


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


class ManagedApplicationLifecycle(Protocol):
    def request_shutdown(self, transaction_id: TransactionId) -> None: ...

    def launch(self, *, version_root: Path, transaction_id: TransactionId, launch_attempt_id: str, expected_version: str) -> None: ...
