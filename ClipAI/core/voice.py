from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ClipAI.core.models import PasteTarget


class VoiceLanguage(str):
    """One of the explicitly supported Voice Input V1 recognition languages."""

    def __new__(cls, value: str) -> VoiceLanguage:
        if value not in SUPPORTED_VOICE_LANGUAGES:
            raise ValueError(f"unsupported Voice Input language: {value}")
        return str.__new__(cls, value)


SUPPORTED_VOICE_LANGUAGES: tuple[str, str] = ("zh-TW", "en-US")


class VoiceSetupId(str):
    """Identity of one explicit Voice Input setup/permission operation."""


class VoiceCaptureId(str):
    """Identity of one admitted push-to-talk capture."""


class VoiceDisableId(str):
    """Identity of one requested Voice Input disable operation."""


class VoiceCapabilityPhase(str, Enum):
    DISABLED = "disabled"
    SETUP_REQUIRED = "setup_required"
    REQUESTING_PERMISSION = "requesting_permission"
    READY = "ready"
    PERMISSION_BLOCKED = "permission_blocked"
    UNAVAILABLE = "unavailable"
    DISABLING = "disabling"
    DISABLE_FAILED = "disable_failed"
    CLEANUP_UNCONFIRMED = "cleanup_unconfirmed"


class VoiceCapturePhase(str, Enum):
    STARTING = "starting"
    LISTENING = "listening"
    STOP_REQUESTED = "stop_requested"
    FINALIZING = "finalizing"
    CANCEL_REQUESTED = "cancel_requested"
    TERMINAL = "terminal"


class VoiceTransportFailure(str, Enum):
    PERMISSION_DENIED = "permission_denied"
    PERMISSION_BLOCKED = "permission_blocked"
    UNAVAILABLE = "unavailable"
    INITIALIZATION_FAILED = "initialization_failed"
    PROCESS_CRASHED = "process_crashed"
    PROTOCOL_ERROR = "protocol_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class VoiceEngineSetupReady:
    setup_id: VoiceSetupId


@dataclass(frozen=True)
class VoiceEngineSetupBlocked:
    setup_id: VoiceSetupId
    failure: VoiceTransportFailure = VoiceTransportFailure.PERMISSION_BLOCKED


@dataclass(frozen=True)
class VoiceEngineSetupFailed:
    setup_id: VoiceSetupId
    failure: VoiceTransportFailure
    detail: str = ""


@dataclass(frozen=True)
class VoiceEngineListening:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class VoiceEngineInterim:
    capture_id: VoiceCaptureId
    text: str


@dataclass(frozen=True)
class VoiceEngineFinalSegment:
    capture_id: VoiceCaptureId
    sequence: int
    text: str

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("Voice Input final-segment sequence must be non-negative")


@dataclass(frozen=True)
class VoiceEngineEnded:
    capture_id: VoiceCaptureId


@dataclass(frozen=True)
class VoiceEngineFailed:
    capture_id: VoiceCaptureId
    failure: VoiceTransportFailure
    detail: str = ""


VoiceEngineEvent = (
    VoiceEngineSetupReady
    | VoiceEngineSetupBlocked
    | VoiceEngineSetupFailed
    | VoiceEngineListening
    | VoiceEngineInterim
    | VoiceEngineFinalSegment
    | VoiceEngineEnded
    | VoiceEngineFailed
)


@dataclass(frozen=True)
class VoiceDraftTarget:
    """A capture-time insertion target owned by a Voice Workflow origin."""

    workflow_id: str
    expected_revision: int
    paste_target: PasteTarget
    selection_start: int
    selection_end: int

    def __post_init__(self) -> None:
        if self.selection_start < 0 or self.selection_end < self.selection_start:
            raise ValueError("Voice Input selection range is invalid")


@dataclass(frozen=True)
class VoiceOrigin:
    """Workflow-owned, ephemeral canonical Voice Input draft."""

    paste_target: PasteTarget
    text: str = ""
    revision: int = 0


@dataclass(frozen=True)
class VoiceProjection:
    """Owner-produced state safe for UI and Tray projection."""

    capability: VoiceCapabilityPhase
    language: VoiceLanguage
    capture_id: VoiceCaptureId | None = None
    capture_phase: VoiceCapturePhase | None = None
    interim_text: str = ""
    message: str = ""
    workflow_id: str | None = None
