from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Protocol
import uuid

from ClipAI.core.models import (
    PressType,
    RecipeActiveRevision,
    RecipeBuiltinUpdateDecision,
    RecipePromptCandidate,
    RecipeRevision,
    RecipeRevisionSnapshot,
)
from ClipAI.services.action_catalog import ActionCatalog


class RecipeRevisionStore(Protocol):
    def load(self) -> RecipeRevisionSnapshot: ...

    def save(self, snapshot: RecipeRevisionSnapshot) -> None: ...


class RecipeRevisionCoordinator:
    def __init__(
        self,
        actions: ActionCatalog,
        store: RecipeRevisionStore,
        *,
        now: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._actions = actions
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._snapshot = store.load()
        try:
            self._publish_snapshot(self._snapshot)
        except (KeyError, ValueError):
            self._actions.restore_all_builtins()
            raise

    def apply(
        self,
        candidate: RecipePromptCandidate,
        validation_summary: str,
    ) -> RecipeRevision:
        current = self._actions.resolve(candidate.action_id, candidate.press_type)
        if current.version_id != candidate.parent_version:
            raise ValueError("candidate parent version is no longer current")
        preview = self._actions.preview_prompts(
            candidate.action_id,
            candidate.press_type,
            candidate.system_prompt,
            candidate.prompt,
        )
        revision = RecipeRevision(
            revision_id=self._new_id(),
            action_id=candidate.action_id,
            press_type=candidate.press_type,
            parent_version=candidate.parent_version,
            version_id=preview.version_id,
            created_at=self._now().isoformat(),
            system_prompt=candidate.system_prompt,
            prompt=candidate.prompt,
            validation_summary=validation_summary.strip(),
            provider=candidate.provider,
            model=candidate.model,
        )
        snapshot = RecipeRevisionSnapshot(
            schema_version=self._snapshot.schema_version,
            revisions=(*self._snapshot.revisions, revision),
            active=self._replace_active(
                self._snapshot.active,
                RecipeActiveRevision(
                    revision.action_id,
                    revision.press_type,
                    revision.revision_id,
                ),
            ),
            builtin_update_decisions=self._snapshot.builtin_update_decisions,
        )
        self._store.save(snapshot)
        try:
            self._actions.activate_prompts(
                revision.action_id,
                revision.press_type,
                revision.system_prompt,
                revision.prompt,
            )
        except BaseException:
            self._store.save(self._snapshot)
            self._publish_snapshot(self._snapshot)
            raise
        self._snapshot = snapshot
        return revision

    def history(
        self,
        action_id: str,
        press_type: PressType,
    ) -> tuple[RecipeRevision, ...]:
        builtin = self._actions.resolve_builtin(action_id, press_type)
        builtin_revision = RecipeRevision(
            revision_id=f"builtin:{builtin.version_id}",
            action_id=action_id,
            press_type=press_type,
            parent_version="",
            version_id=builtin.version_id,
            created_at="",
            system_prompt=builtin.system_prompt,
            prompt=builtin.prompt,
            validation_summary="ClipAI 內建版本",
            source="builtin",
        )
        personal = tuple(
            revision
            for revision in self._snapshot.revisions
            if revision.action_id == action_id and revision.press_type == press_type
        )
        return (builtin_revision, *personal)

    def active_revision_id(
        self,
        action_id: str,
        press_type: PressType,
    ) -> str:
        active = next(
            (
                item
                for item in self._snapshot.active
                if item.action_id == action_id and item.press_type == press_type
            ),
            None,
        )
        if active is not None and not active.revision_id.startswith("builtin:"):
            return active.revision_id
        builtin = self._actions.resolve_builtin(action_id, press_type)
        return f"builtin:{builtin.version_id}"

    def restore(
        self,
        action_id: str,
        press_type: PressType,
        revision_id: str,
    ) -> RecipeRevision:
        revision = next(
            (
                item
                for item in self.history(action_id, press_type)
                if item.revision_id == revision_id
            ),
            None,
        )
        if revision is None:
            raise ValueError("unknown Recipe revision")
        snapshot = replace(
            self._snapshot,
            active=self._replace_active(
                self._snapshot.active,
                RecipeActiveRevision(action_id, press_type, revision_id),
            ),
        )
        self._store.save(snapshot)
        try:
            if revision.source == "builtin":
                self._actions.restore_builtin(action_id, press_type)
            else:
                self._actions.activate_prompts(
                    action_id,
                    press_type,
                    revision.system_prompt,
                    revision.prompt,
                )
        except BaseException:
            self._store.save(self._snapshot)
            self._publish_snapshot(self._snapshot)
            raise
        self._snapshot = snapshot
        return revision

    def builtin_update_available(
        self,
        action_id: str,
        press_type: PressType,
    ) -> bool:
        active = next(
            (
                item
                for item in self._snapshot.active
                if item.action_id == action_id and item.press_type == press_type
            ),
            None,
        )
        if active is None or active.revision_id.startswith("builtin:"):
            return False
        revisions = {
            revision.revision_id: revision
            for revision in self._snapshot.revisions
        }
        by_version = {
            revision.version_id: revision
            for revision in self._snapshot.revisions
            if revision.action_id == action_id
            and revision.press_type == press_type
        }
        revision = revisions.get(active.revision_id)
        if revision is None:
            return False
        parent_version = revision.parent_version
        while parent_version in by_version:
            parent_version = by_version[parent_version].parent_version
        builtin_version = self._actions.resolve_builtin(
            action_id,
            press_type,
        ).version_id
        if parent_version == builtin_version:
            return False
        return not any(
            decision.action_id == action_id
            and decision.press_type == press_type
            and decision.builtin_version == builtin_version
            for decision in self._snapshot.builtin_update_decisions
        )

    def keep_personal_after_builtin_update(
        self,
        action_id: str,
        press_type: PressType,
    ) -> None:
        builtin_version = self._actions.resolve_builtin(
            action_id,
            press_type,
        ).version_id
        decision = RecipeBuiltinUpdateDecision(
            action_id,
            press_type,
            builtin_version,
        )
        decisions = (
            *(
                item
                for item in self._snapshot.builtin_update_decisions
                if (item.action_id, item.press_type)
                != (action_id, press_type)
            ),
            decision,
        )
        snapshot = replace(
            self._snapshot,
            builtin_update_decisions=decisions,
        )
        self._store.save(snapshot)
        self._snapshot = snapshot

    def _publish_snapshot(self, snapshot: RecipeRevisionSnapshot) -> None:
        revisions = {revision.revision_id: revision for revision in snapshot.revisions}
        active_keys: set[tuple[str, PressType]] = set()
        for active in snapshot.active:
            key = (active.action_id, active.press_type)
            if key in active_keys:
                raise ValueError("duplicate active Recipe revision")
            active_keys.add(key)
            self._actions.resolve_builtin(active.action_id, active.press_type)
            if active.revision_id.startswith("builtin:"):
                continue
            revision = revisions.get(active.revision_id)
            if (
                revision is None
                or revision.action_id != active.action_id
                or revision.press_type != active.press_type
            ):
                raise ValueError("active Recipe revision does not exist")
        self._actions.restore_all_builtins()
        for active in snapshot.active:
            if active.revision_id.startswith("builtin:"):
                continue
            revision = revisions.get(active.revision_id)
            assert revision is not None
            self._actions.activate_prompts(
                revision.action_id,
                revision.press_type,
                revision.system_prompt,
                revision.prompt,
            )

    @staticmethod
    def _replace_active(
        active: tuple[RecipeActiveRevision, ...],
        replacement: RecipeActiveRevision,
    ) -> tuple[RecipeActiveRevision, ...]:
        return (
            *(
                item
                for item in active
                if (item.action_id, item.press_type)
                != (replacement.action_id, replacement.press_type)
            ),
            replacement,
        )
