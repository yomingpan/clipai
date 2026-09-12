from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManagedInstallMarker:
    managed_install_id: str
    install_root: Path
    shared_root: Path
    launcher_version: str
    key_id: str


@dataclass(frozen=True)
class ManagedInstallState:
    managed_install_id: str
    revision: int
    current_version: str
    previous_version: str | None
