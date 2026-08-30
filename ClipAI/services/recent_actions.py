from __future__ import annotations

from ClipAI.core.models import EntryActionRef


class RecentActionHistory:
    def __init__(self, refs: tuple[EntryActionRef, ...] = ()) -> None:
        unique: list[EntryActionRef] = []
        for ref in refs:
            if any(item.action_id == ref.action_id for item in unique):
                continue
            unique.append(ref)
        self._refs = tuple(unique[:3])

    @property
    def refs(self) -> tuple[EntryActionRef, ...]:
        return self._refs

    def record(self, ref: EntryActionRef) -> tuple[EntryActionRef, ...]:
        self._refs = (
            ref,
            *(item for item in self._refs if item.action_id != ref.action_id),
        )[:3]
        return self._refs
