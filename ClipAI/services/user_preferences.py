from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import threading
from typing import Literal

from ClipAI.core.models import GuidancePreferences, SpeechSpeed, SpeechSpeedState, UserPreferences, VoiceLanguagePreference, VoicePreferencesState
from ClipAI.core.ports import UserPreferencesStore

logger = logging.getLogger("clipai.user_preferences")

SPEECH_SPEED_RATES: dict[SpeechSpeed, str] = {
    "slow": "-25%",
    "normal": "+0%",
    "fast": "+25%",
    "super_fast": "+50%",
}
_SPEECH_SPEED_BY_RATE = {rate: speed for speed, rate in SPEECH_SPEED_RATES.items()}
PreferenceOperationKind = Literal["set_guidance_enabled", "reset_guidance", "set_speech_speed", "set_voice_enabled", "set_voice_language"]


@dataclass(frozen=True)
class UserPreferencesWork:
    operation_id: str
    kind: PreferenceOperationKind
    enabled: bool | None = None
    speed: SpeechSpeed | None = None
    voice_language: VoiceLanguagePreference | None = None


@dataclass(frozen=True)
class UserPreferencesUpdate:
    guidance: GuidancePreferences
    speech_speed: SpeechSpeedState
    voice: VoicePreferencesState
    work: UserPreferencesWork | None = None
    ignored: bool = False
    error: str = ""


class UserPreferencesCoordinator:
    """Single owner for persisted user preferences and their save lifecycle."""

    def __init__(
        self,
        store: UserPreferencesStore,
        *,
        base_speech_rate: str = "+0%",
        speech_available: bool = True,
    ) -> None:
        self._store = store
        self._lock = threading.RLock()
        self._preferences = store.load()
        self._base_speech_rate = base_speech_rate
        self._speech_available = speech_available
        self._pending: UserPreferencesWork | None = None

    @property
    def guidance_preferences(self) -> GuidancePreferences:
        with self._lock:
            return self._guidance_projection()

    @property
    def speech_speed_state(self) -> SpeechSpeedState:
        with self._lock:
            return self._speech_projection()

    @property
    def voice_preferences(self) -> VoicePreferencesState:
        with self._lock:
            return self._voice_projection()

    def current_speech_rate(self) -> str:
        with self._lock:
            speed = self._preferences.speech_speed
            return SPEECH_SPEED_RATES[speed] if speed is not None else self._base_speech_rate

    def begin_set_guidance_enabled(self, enabled: bool, operation_id: str) -> UserPreferencesUpdate:
        return self._begin(UserPreferencesWork(operation_id, "set_guidance_enabled", enabled=enabled))

    def begin_reset_guidance(self, operation_id: str) -> UserPreferencesUpdate:
        return self._begin(UserPreferencesWork(operation_id, "reset_guidance"))

    def begin_set_speech_speed(self, speed: SpeechSpeed, operation_id: str) -> UserPreferencesUpdate:
        with self._lock:
            if not self._speech_available or speed == self._selected_speech_speed():
                return self._update(ignored=True)
        return self._begin(UserPreferencesWork(operation_id, "set_speech_speed", speed=speed))

    def begin_set_voice_enabled(self, enabled: bool, operation_id: str) -> UserPreferencesUpdate:
        with self._lock:
            if self._preferences.voice_input_enabled == enabled:
                return self._update(ignored=True)
        return self._begin(UserPreferencesWork(operation_id, "set_voice_enabled", enabled=enabled))

    def begin_set_voice_language(self, language: VoiceLanguagePreference, operation_id: str) -> UserPreferencesUpdate:
        with self._lock:
            if self._preferences.voice_language == language:
                return self._update(ignored=True)
        return self._begin(UserPreferencesWork(operation_id, "set_voice_language", voice_language=language))

    def _begin(self, work: UserPreferencesWork) -> UserPreferencesUpdate:
        with self._lock:
            if self._pending is not None:
                return self._update(ignored=True)
            self._pending = work
            return self._update(work=work)

    def execute(self, work: UserPreferencesWork) -> str:
        try:
            with self._lock:
                if self._pending != work:
                    return ""
                current = self._preferences
                if work.kind == "set_guidance_enabled":
                    desired = replace(current, first_use_hints_enabled=bool(work.enabled))
                elif work.kind == "reset_guidance":
                    desired = replace(current, seen_action_ids=frozenset())
                elif work.kind == "set_speech_speed" and work.speed is not None:
                    desired = replace(current, speech_speed=work.speed)
                elif work.kind == "set_voice_enabled" and work.enabled is not None:
                    desired = replace(current, voice_input_enabled=work.enabled)
                elif work.kind == "set_voice_language" and work.voice_language is not None:
                    desired = replace(current, voice_language=work.voice_language)
                else:
                    raise ValueError(f"unsupported user preference operation: {work.kind}")
                self._store.save(desired)
                self._preferences = desired
        except (OSError, TypeError, ValueError):
            logger.exception("Unable to persist user preferences")
            if work.kind == "set_speech_speed":
                return "Could not save speech speed. The previous speed remains active."
            return "無法儲存使用引導設定，請再試一次。"
        return ""

    def complete(self, operation_id: str, error: str = "") -> UserPreferencesUpdate:
        with self._lock:
            if self._pending is None or self._pending.operation_id != operation_id:
                return self._update(ignored=True)
            self._pending = None
            return self._update(error=error)

    def consume_first_use_hint(self, action_id: str) -> bool:
        with self._lock:
            current = self._preferences
            if not current.first_use_hints_enabled or action_id in current.seen_action_ids:
                return False
            desired = replace(current, seen_action_ids=current.seen_action_ids | {action_id})
            try:
                self._store.save(desired)
            except OSError:
                logger.exception("Unable to mark first-use guidance as seen action_id=%s", action_id)
                return True
            self._preferences = desired
            return True

    def _selected_speech_speed(self) -> SpeechSpeed | None:
        return self._preferences.speech_speed or _SPEECH_SPEED_BY_RATE.get(self._base_speech_rate)

    def _guidance_projection(self) -> GuidancePreferences:
        current = self._preferences
        return GuidancePreferences(
            current.first_use_hints_enabled,
            current.seen_action_ids,
            update_pending=self._pending is not None,
        )

    def _speech_projection(self) -> SpeechSpeedState:
        pending_speed = self._pending.speed if self._pending is not None and self._pending.kind == "set_speech_speed" else None
        return SpeechSpeedState(
            selected_speed=self._selected_speech_speed(),
            pending_speed=pending_speed,
            update_pending=self._pending is not None,
            available=self._speech_available,
        )

    def _voice_projection(self) -> VoicePreferencesState:
        return VoicePreferencesState(
            self._preferences.voice_input_enabled,
            self._preferences.voice_language,
            update_pending=self._pending is not None and self._pending.kind in {"set_voice_enabled", "set_voice_language"},
        )

    def _update(
        self,
        *,
        work: UserPreferencesWork | None = None,
        ignored: bool = False,
        error: str = "",
    ) -> UserPreferencesUpdate:
        return UserPreferencesUpdate(
            self._guidance_projection(),
            self._speech_projection(),
            self._voice_projection(),
            work=work,
            ignored=ignored,
            error=error,
        )
