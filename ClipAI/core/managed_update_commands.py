from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from ClipAI.core.managed_update import LaunchAttemptId, TransactionId


@dataclass(frozen=True)
class InstallManagedCommand:
    shared_root: Path
    install_root: Path
    transaction_id: TransactionId
    expected_version: str
    bundle_path: Path
    bundle_size: int
    bundle_sha256: str
    manifest_sha256: str
    key_id: str
    managed_install_id: str
    launcher_version: str
    base_python: Path


@dataclass(frozen=True)
class LaunchManagedCommand:
    shared_root: Path
    install_root: Path
    transaction_id: TransactionId
    launch_attempt_id: LaunchAttemptId
    expected_version: str


@dataclass(frozen=True)
class HostManagedCommand:
    shared_root: Path
    install_root: Path
    transaction_id: TransactionId
    base_python: Path


@dataclass(frozen=True)
class SelfcheckManagedCommand:
    shared_root: Path
    install_root: Path
    transaction_id: TransactionId


ManagedCommand: TypeAlias = (
    InstallManagedCommand
    | LaunchManagedCommand
    | HostManagedCommand
    | SelfcheckManagedCommand
)
