from __future__ import annotations

from ClipAI.core.models import OutputProfile


class OutputProfileCatalog:
    def __init__(self, profiles: list[OutputProfile]) -> None:
        self._profiles = {profile.id: profile for profile in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("output profile ids must be unique")
        if "plain_text" not in self._profiles:
            self._profiles["plain_text"] = OutputProfile("plain_text", "")

    def get(self, profile_id: str) -> OutputProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"unknown output profile: {profile_id}") from exc

    def contains(self, profile_id: str) -> bool:
        return profile_id in self._profiles
