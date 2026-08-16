from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import threading
import uuid

from ClipAI.core.errors import PersonalStyleUnavailableError
from ClipAI.core.models import (
    PersonalStyleCollection,
    PersonalStyleOption,
    PersonalStyleProfile,
    PersonalStyleState,
    ResolvedAction,
)
from ClipAI.core.ports import PersonalStyleFileReader, PersonalStyleStore


MAX_PERSONAL_STYLE_CHARACTERS = 24_000
_SUPPORTED_SUFFIXES = frozenset({".md", ".txt"})


@dataclass(frozen=True)
class PersonalStyleWork:
    operation_id: str
    kind: str
    path: str = ""
    profile_id: str = ""


@dataclass(frozen=True)
class PersonalStyleUpdate:
    state: PersonalStyleState
    work: PersonalStyleWork | None = None
    ignored: bool = False


class PersonalStyleCoordinator:
    """Single owner of imported style profiles, selection, and save lifecycle."""

    def __init__(self, store: PersonalStyleStore, file_reader: PersonalStyleFileReader) -> None:
        self._store = store
        self._file_reader = file_reader
        self._lock = threading.RLock()
        self._collection = self._normalize(store.load())
        self._pending: PersonalStyleWork | None = None
        self._last_operation_kind: str | None = None
        self._last_message = ""
        self._last_failed = False

    @property
    def state(self) -> PersonalStyleState:
        with self._lock:
            return self._state()

    def begin_import(self, path: str, operation_id: str) -> PersonalStyleUpdate:
        return self._begin(PersonalStyleWork(operation_id, "import", path=path))

    def begin_select(self, profile_id: str, operation_id: str) -> PersonalStyleUpdate:
        with self._lock:
            if profile_id == self._collection.selected_profile_id:
                return PersonalStyleUpdate(self._state(), ignored=True)
            if not any(profile.profile_id == profile_id for profile in self._collection.profiles):
                return PersonalStyleUpdate(self._state(), ignored=True)
        return self._begin(PersonalStyleWork(operation_id, "select", profile_id=profile_id))

    def _begin(self, work: PersonalStyleWork) -> PersonalStyleUpdate:
        with self._lock:
            if self._pending is not None:
                return PersonalStyleUpdate(self._state(), ignored=True)
            self._pending = work
            self._last_operation_kind = None
            self._last_message = ""
            self._last_failed = False
            return PersonalStyleUpdate(self._state(), work=work)

    def execute(self, work: PersonalStyleWork) -> str:
        try:
            with self._lock:
                if self._pending != work:
                    return ""
                current = self._collection
            desired, success_message = self._desired_collection(current, work)
            self._store.save(desired)
            with self._lock:
                if self._pending == work:
                    self._collection = desired
                    self._last_message = success_message
            return ""
        except (OSError, UnicodeError, ValueError) as exc:
            return str(exc) or "Unable to save the personal style."

    def complete(self, operation_id: str, error: str = "") -> PersonalStyleUpdate:
        with self._lock:
            if self._pending is None or self._pending.operation_id != operation_id:
                return PersonalStyleUpdate(self._state(), ignored=True)
            work = self._pending
            self._pending = None
            self._last_operation_kind = work.kind
            self._last_message = error or self._last_message
            self._last_failed = bool(error)
            return PersonalStyleUpdate(self._state())

    def bind(self, action: ResolvedAction) -> ResolvedAction:
        if action.personal_style_mode is None:
            return action
        with self._lock:
            profile = next(
                (
                    item
                    for item in self._collection.profiles
                    if item.profile_id == self._collection.selected_profile_id
                ),
                None,
            )
        if profile is None:
            raise PersonalStyleUnavailableError(
                "尚未選擇個人風格。請先在 Personal Styles 匯入或選擇一份 profile。"
            )
        return self.bind_to(action, profile)

    @staticmethod
    def bind_to(action: ResolvedAction, profile: PersonalStyleProfile) -> ResolvedAction:
        if action.personal_style_mode is None:
            return action
        version = hashlib.sha256(
            f"{action.version_id}:{profile.profile_id}:{profile.content_hash}".encode("utf-8")
        ).hexdigest()
        return replace(action, personal_style=profile, version_id=version)

    def _desired_collection(
        self,
        current: PersonalStyleCollection,
        work: PersonalStyleWork,
    ) -> tuple[PersonalStyleCollection, str]:
        if work.kind == "select":
            profile = next(
                (item for item in current.profiles if item.profile_id == work.profile_id),
                None,
            )
            if profile is None:
                raise ValueError("The selected personal style no longer exists.")
            return replace(current, selected_profile_id=profile.profile_id), f"Using {profile.name}."
        if work.kind != "import":
            raise ValueError(f"Unsupported personal style operation: {work.kind}")
        source = Path(work.path)
        if source.suffix.lower() not in _SUPPORTED_SUFFIXES:
            raise ValueError("Personal Styles accepts Markdown (.md) or plain text (.txt) files.")
        guide = self._file_reader.read_text(work.path).strip()
        if not guide:
            raise ValueError("The selected style guide is empty.")
        if len(guide) > MAX_PERSONAL_STYLE_CHARACTERS:
            raise ValueError(
                f"The style guide is too long ({len(guide):,} characters). "
                f"Please reduce it to {MAX_PERSONAL_STYLE_CHARACTERS:,} characters or fewer."
            )
        name = source.stem.strip()
        if not name:
            raise ValueError("The style guide needs a file name.")
        content_hash = hashlib.sha256(guide.encode("utf-8")).hexdigest()
        existing = next((item for item in current.profiles if item.name.casefold() == name.casefold()), None)
        profile = PersonalStyleProfile(
            existing.profile_id if existing is not None else uuid.uuid4().hex,
            name,
            guide,
            content_hash,
        )
        profiles = tuple(
            profile if item.profile_id == profile.profile_id else item
            for item in current.profiles
        )
        if existing is None:
            profiles = (*profiles, profile)
        selected_id = current.selected_profile_id or profile.profile_id
        verb = "Updated" if existing is not None else "Imported"
        message = f"{verb} {name}."
        if not current.selected_profile_id:
            message += " It is now the active style."
        return PersonalStyleCollection(profiles, selected_id), message

    def _state(self) -> PersonalStyleState:
        operation = self._pending
        operation_state = "pending" if operation is not None else (
            "failed" if self._last_failed else (
                "succeeded" if self._last_operation_kind is not None else "idle"
            )
        )
        return PersonalStyleState(
            tuple(PersonalStyleOption(profile.profile_id, profile.name) for profile in self._collection.profiles),
            self._collection.selected_profile_id,
            operation_state=operation_state,
            operation_kind=(operation.kind if operation is not None else self._last_operation_kind),
            operation_id=(operation.operation_id if operation is not None else ""),
            message=(
                "Importing style guide..."
                if operation is not None and operation.kind == "import"
                else "Saving active style..."
                if operation is not None
                else self._last_message
            ),
        )

    @staticmethod
    def _normalize(collection: PersonalStyleCollection) -> PersonalStyleCollection:
        profile_ids = {profile.profile_id for profile in collection.profiles}
        selected = collection.selected_profile_id if collection.selected_profile_id in profile_ids else ""
        return replace(collection, selected_profile_id=selected)
