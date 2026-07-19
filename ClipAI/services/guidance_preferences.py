from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import threading

from ClipAI.core.models import GuidancePreferences
from ClipAI.core.ports import GuidancePreferencesStore

logger = logging.getLogger("clipai.guidance_preferences")


@dataclass(frozen=True)
class GuidancePreferencesWork:
    operation_id: str
    kind: str
    enabled: bool | None = None


@dataclass(frozen=True)
class GuidancePreferencesUpdate:
    preferences: GuidancePreferences
    work: GuidancePreferencesWork | None = None
    ignored: bool = False
    error: str = ""


class GuidancePreferencesCoordinator:
    """Single owner for persisted first-use guidance state and its lifecycle."""

    def __init__(self, store: GuidancePreferencesStore) -> None:
        self._store = store
        self._lock = threading.RLock()
        self._preferences = store.load()
        self._pending_operation_id = ""

    @property
    def preferences(self) -> GuidancePreferences:
        with self._lock:
            return self._preferences

    def begin_set_enabled(self, enabled: bool, operation_id: str) -> GuidancePreferencesUpdate:
        return self._begin(GuidancePreferencesWork(operation_id, "set_enabled", enabled))

    def begin_reset(self, operation_id: str) -> GuidancePreferencesUpdate:
        return self._begin(GuidancePreferencesWork(operation_id, "reset"))

    def _begin(self, work: GuidancePreferencesWork) -> GuidancePreferencesUpdate:
        with self._lock:
            if self._pending_operation_id:
                return GuidancePreferencesUpdate(self._preferences, ignored=True)
            self._pending_operation_id = work.operation_id
            pending = replace(self._preferences, update_pending=True)
            return GuidancePreferencesUpdate(pending, work=work)

    def execute(self, work: GuidancePreferencesWork) -> str:
        try:
            with self._lock:
                current = self._preferences
                if work.kind == "set_enabled":
                    desired = replace(current, first_use_hints_enabled=bool(work.enabled), update_pending=False)
                elif work.kind == "reset":
                    desired = replace(current, seen_action_ids=frozenset(), update_pending=False)
                else:
                    raise ValueError(f"unsupported guidance preference operation: {work.kind}")
                self._store.save(desired)
                self._preferences = desired
        except (OSError, ValueError):
            logger.exception("Unable to persist guidance preferences")
            return "無法儲存使用引導設定，請再試一次。"
        return ""

    def complete(self, operation_id: str, error: str = "") -> GuidancePreferencesUpdate:
        with self._lock:
            if self._pending_operation_id != operation_id:
                return GuidancePreferencesUpdate(self._preferences, ignored=True)
            self._pending_operation_id = ""
            if error:
                return GuidancePreferencesUpdate(self._preferences, error=error)
            return GuidancePreferencesUpdate(self._preferences)

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
