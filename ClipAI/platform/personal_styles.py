from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from ClipAI.core.models import PersonalStyleCollection, PersonalStyleProfile


class Utf8PersonalStyleFileReader:
    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8-sig")


class JsonPersonalStyleStore:
    def __init__(self, path: str | Path = "data/personal_styles.json") -> None:
        self._path = Path(path)

    def load(self) -> PersonalStyleCollection:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return PersonalStyleCollection()
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return PersonalStyleCollection()
        raw_profiles = payload.get("profiles")
        selected = payload.get("selected_profile_id")
        if not isinstance(raw_profiles, list) or not isinstance(selected, str):
            return PersonalStyleCollection()
        profiles: list[PersonalStyleProfile] = []
        ids: set[str] = set()
        for item in raw_profiles:
            if not isinstance(item, dict):
                return PersonalStyleCollection()
            profile_id, name, guide = item.get("id"), item.get("name"), item.get("guide")
            if not all(isinstance(value, str) and value.strip() for value in (profile_id, name, guide)):
                return PersonalStyleCollection()
            if profile_id in ids:
                return PersonalStyleCollection()
            ids.add(profile_id)
            profiles.append(
                PersonalStyleProfile(
                    profile_id,
                    name,
                    guide,
                    hashlib.sha256(guide.encode("utf-8")).hexdigest(),
                )
            )
        return PersonalStyleCollection(tuple(profiles), selected if selected in ids else "")

    def save(self, collection: PersonalStyleCollection) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "selected_profile_id": collection.selected_profile_id,
            "profiles": [
                {"id": profile.profile_id, "name": profile.name, "guide": profile.guide}
                for profile in collection.profiles
            ],
        }
        temporary_path: Path | None = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                dir=self._path.parent,
            )
            temporary_path = Path(temporary)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
