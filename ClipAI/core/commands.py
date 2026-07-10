from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ClipAI.core.models import PressType


@dataclass(frozen=True)
class StartAction:
    action_id: str
    press_type: PressType


@dataclass(frozen=True)
class CloseSession:
    session_id: str


@dataclass(frozen=True)
class CancelSession:
    session_id: str


@dataclass(frozen=True)
class CopyResult:
    session_id: str


@dataclass(frozen=True)
class FollowUp:
    session_id: str
    text: str


@dataclass(frozen=True)
class TogglePin:
    session_id: str


@dataclass(frozen=True)
class ShutdownApplication:
    pass


AppCommand: TypeAlias = StartAction | CloseSession | CancelSession | CopyResult | FollowUp | TogglePin | ShutdownApplication
