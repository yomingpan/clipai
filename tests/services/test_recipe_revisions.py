from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ClipAI.core.models import ActionDefinition, RecipePromptCandidate
from ClipAI.core.models import RecipeActiveRevision
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.recipe_revisions import (
    RecipeRevisionCoordinator,
    RecipeRevisionSnapshot,
)


class MemoryRevisionStore:
    def __init__(self) -> None:
        self.snapshot = RecipeRevisionSnapshot()
        self.saved: list[RecipeRevisionSnapshot] = []
        self.fail = False

    def load(self) -> RecipeRevisionSnapshot:
        return self.snapshot

    def save(self, snapshot: RecipeRevisionSnapshot) -> None:
        if self.fail:
            raise OSError("disk full")
        self.snapshot = snapshot
        self.saved.append(snapshot)


class FailingActivationCatalog(ActionCatalog):
    def __init__(self, actions) -> None:
        super().__init__(actions)
        self.fail_activation = False

    def activate_prompts(self, action_id, press_type, system_prompt, prompt):
        resolved = super().activate_prompts(
            action_id,
            press_type,
            system_prompt,
            prompt,
        )
        if self.fail_activation:
            raise RuntimeError("publish failed")
        return resolved


def catalog() -> ActionCatalog:
    return ActionCatalog(
        [
            ActionDefinition(
                id="rewrite",
                name="Rewrite",
                system_prompt="Original system",
                prompt="Original {input}",
                press_variants={},
                temperature=0.4,
                output_profile="markdown",
            )
        ]
    )


def candidate(parent: str, *, iteration: int = 1) -> RecipePromptCandidate:
    return RecipePromptCandidate(
        action_id="rewrite",
        press_type="short",
        parent_version=parent,
        iteration=iteration,
        system_prompt="Improved system",
        prompt="Improved {input}",
        explanation="更清楚。",
        provider="openai",
        model="gpt-test",
    )


def test_apply_persists_immutable_revision_and_active_pointer_before_hot_publish() -> None:
    actions = catalog()
    original = actions.resolve("rewrite", "short")
    store = MemoryRevisionStore()
    coordinator = RecipeRevisionCoordinator(
        actions,
        store,
        now=lambda: datetime(2026, 7, 27, tzinfo=timezone.utc),
        new_id=lambda: "revision-1",
    )

    revision = coordinator.apply(candidate(original.version_id), "1／1 比較偏好新版本")

    active = actions.resolve("rewrite", "short")
    assert revision.revision_id == "revision-1"
    assert [(item.action_id, item.press_type, item.revision_id) for item in store.snapshot.active] == [
        ("rewrite", "short", "revision-1")
    ]
    assert store.snapshot.revisions == (revision,)
    assert active.system_prompt == "Improved system"
    assert active.prompt == "Improved {input}"
    assert active.temperature == 0.4
    assert active.output_profile == "markdown"
    assert active.version_id == revision.version_id


def test_failed_persistence_leaves_previous_runtime_version_active() -> None:
    actions = catalog()
    original = actions.resolve("rewrite", "short")
    store = MemoryRevisionStore()
    store.fail = True
    coordinator = RecipeRevisionCoordinator(actions, store)

    with pytest.raises(OSError, match="disk full"):
        coordinator.apply(candidate(original.version_id), "validated")

    assert actions.resolve("rewrite", "short") == original


def test_failed_runtime_activation_rolls_back_durable_pointer_and_catalog() -> None:
    definition = catalog().get("rewrite")
    actions = FailingActivationCatalog([definition])
    original = actions.resolve("rewrite", "short")
    store = MemoryRevisionStore()
    coordinator = RecipeRevisionCoordinator(actions, store)
    actions.fail_activation = True

    with pytest.raises(RuntimeError, match="publish failed"):
        coordinator.apply(candidate(original.version_id), "validated")

    assert store.snapshot == RecipeRevisionSnapshot()
    assert actions.resolve("rewrite", "short") == original


def test_candidate_becomes_stale_after_active_version_changes() -> None:
    actions = catalog()
    parent = actions.resolve("rewrite", "short").version_id
    coordinator = RecipeRevisionCoordinator(
        actions,
        MemoryRevisionStore(),
        new_id=iter(("revision-1", "revision-2")).__next__,
    )
    coordinator.apply(candidate(parent), "validated")

    with pytest.raises(ValueError, match="no longer current"):
        coordinator.apply(candidate(parent, iteration=2), "validated")


def test_history_contains_builtin_and_applied_versions_and_can_restore_builtin() -> None:
    actions = catalog()
    builtin = actions.resolve("rewrite", "short")
    coordinator = RecipeRevisionCoordinator(
        actions,
        MemoryRevisionStore(),
        new_id=lambda: "revision-1",
    )
    revision = coordinator.apply(candidate(builtin.version_id), "validated")

    history = coordinator.history("rewrite", "short")
    assert [item.revision_id for item in history] == [
        f"builtin:{builtin.version_id}",
        revision.revision_id,
    ]

    coordinator.restore("rewrite", "short", f"builtin:{builtin.version_id}")

    assert actions.resolve("rewrite", "short") == builtin


def test_builtin_update_never_overwrites_personal_version_and_keep_choice_is_saved() -> None:
    old_actions = catalog()
    old_builtin = old_actions.resolve("rewrite", "short")
    store = MemoryRevisionStore()
    RecipeRevisionCoordinator(
        old_actions,
        store,
        new_id=lambda: "revision-1",
    ).apply(candidate(old_builtin.version_id), "validated")
    updated_actions = ActionCatalog(
        [
            ActionDefinition(
                id="rewrite",
                name="Rewrite",
                system_prompt="Updated built-in system",
                prompt="Updated built-in {input}",
                press_variants={},
                temperature=0.4,
                output_profile="markdown",
            )
        ]
    )

    coordinator = RecipeRevisionCoordinator(updated_actions, store)

    assert updated_actions.resolve("rewrite", "short").prompt == "Improved {input}"
    assert coordinator.builtin_update_available("rewrite", "short") is True
    coordinator.keep_personal_after_builtin_update("rewrite", "short")
    assert coordinator.builtin_update_available("rewrite", "short") is False
    assert store.snapshot.builtin_update_decisions[0].decision == "keep_personal"


def test_invalid_snapshot_restores_all_builtins_before_reporting_corruption() -> None:
    actions = catalog()
    builtin = actions.resolve("rewrite", "short")
    actions.activate_prompts("rewrite", "short", "leftover", "leftover {input}")
    store = MemoryRevisionStore()
    store.snapshot = RecipeRevisionSnapshot(
        active=(RecipeActiveRevision("rewrite", "short", "missing"),),
    )

    with pytest.raises(ValueError, match="does not exist"):
        RecipeRevisionCoordinator(actions, store)

    assert actions.resolve("rewrite", "short") == builtin
