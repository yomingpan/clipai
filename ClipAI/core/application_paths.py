from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApplicationPaths:
    """Resolved shipped and user-owned paths injected by app composition."""

    application_root: Path
    config_root: Path
    state_root: Path
    secrets_file: Path
    logs_root: Path
    diagnostics_root: Path
    update_root: Path
    recent_actions_file: Path
    voice_profile_root: Path
    instance_name: str = "default"

    def __post_init__(self) -> None:
        path_fields = (
            self.application_root,
            self.config_root,
            self.state_root,
            self.secrets_file,
            self.logs_root,
            self.diagnostics_root,
            self.update_root,
            self.recent_actions_file,
            self.voice_profile_root,
        )
        if any(not path.is_absolute() for path in path_fields):
            raise ValueError("application paths must be absolute")
        if self.config_root == self.state_root:
            raise ValueError("shipped config and user state roots must be separate")
        if not self.instance_name:
            raise ValueError("instance name must not be empty")

    def config_file(self, name: str) -> Path:
        return self.config_root / name

    def state_file(self, name: str) -> Path:
        return self.state_root / name
