from __future__ import annotations

from ClipAI.core.models import (
    ActionDefinition,
    ActionFeedbackRecord,
    ActionVariant,
)
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.recipe_improvement import RecipeImprovementEvidenceService


class MemoryFeedbackHistory:
    def __init__(self, records: tuple[ActionFeedbackRecord, ...]) -> None:
        self._records = records

    def load(self) -> tuple[ActionFeedbackRecord, ...]:
        return self._records


def make_action(
    *,
    action_id: str = "rewrite",
    input_mode: str = "selection_or_clipboard",
    with_long_variant: bool = True,
) -> ActionDefinition:
    variants = {}
    if with_long_variant:
        variants["long"] = ActionVariant(
            name="Detailed rewrite",
            system_prompt="Keep all details.",
            prompt="Rewrite carefully:\n\n{input}",
        )
    return ActionDefinition(
        id=action_id,
        name="Rewrite",
        system_prompt="Be concise.",
        prompt="Rewrite:\n\n{input}",
        press_variants=variants,
        input_mode=input_mode,
    )


def feedback(
    feedback_id: str,
    *,
    version: str,
    press_type: str = "short",
    outcome: str = "needs_adjustment",
    saved_case: bool = True,
) -> ActionFeedbackRecord:
    return ActionFeedbackRecord(
        record_schema_version=1,
        feedback_id=feedback_id,
        created_at=f"2026-07-{feedback_id[-1]}T00:00:00+00:00",
        workflow_id=f"workflow-{feedback_id}",
        step_id=f"step-{feedback_id}",
        action_id="rewrite",
        action_version=version,
        press_type=press_type,
        provider="openai",
        model="gpt-test",
        input_source="selection",
        outcome=outcome,
        reason="too_long" if outcome == "needs_adjustment" else "",
        note="Keep the conclusion.",
        input_text="Original" if saved_case else None,
        result_text="Result" if saved_case else None,
    )


def test_overview_groups_independent_short_and_explicit_long_variants() -> None:
    catalog = ActionCatalog([make_action()])
    short = catalog.resolve("rewrite", "short")
    long = catalog.resolve("rewrite", "long")
    history = MemoryFeedbackHistory(
        (
            feedback("1", version=short.version_id),
            feedback("2", version=long.version_id, press_type="long", outcome="helpful"),
            feedback("3", version="obsolete-version"),
        )
    )

    overview = RecipeImprovementEvidenceService(catalog, history).overview()

    assert [(item.action_id, item.press_type) for item in overview.variants] == [
        ("rewrite", "short"),
        ("rewrite", "long"),
    ]
    assert overview.variants[0].current_version == short.version_id
    assert overview.variants[0].feedback_count == 1
    assert overview.variants[0].saved_case_count == 1
    assert overview.variants[0].negative_feedback_count == 1
    assert overview.variants[1].current_version == long.version_id
    assert overview.variants[1].feedback_count == 1
    assert overview.variants[1].helpful_feedback_count == 1


def test_reminder_requires_negative_feedback_and_three_saved_current_version_cases() -> None:
    catalog = ActionCatalog([make_action(with_long_variant=False)])
    version = catalog.resolve("rewrite", "short").version_id
    service = RecipeImprovementEvidenceService(
        catalog,
        MemoryFeedbackHistory(
            (
                feedback("1", version=version),
                feedback("2", version=version, outcome="helpful"),
                feedback("3", version=version, outcome="helpful"),
            )
        ),
    )

    summary = service.overview().variants[0]

    assert summary.reminder_recommended is True


def test_feedback_without_saved_content_counts_as_feedback_but_not_as_case() -> None:
    catalog = ActionCatalog([make_action(with_long_variant=False)])
    version = catalog.resolve("rewrite", "short").version_id

    summary = RecipeImprovementEvidenceService(
        catalog,
        MemoryFeedbackHistory((feedback("1", version=version, saved_case=False),)),
    ).overview().variants[0]

    assert summary.feedback_count == 1
    assert summary.saved_case_count == 0
    assert summary.reminder_recommended is False


def test_image_only_recipe_is_visible_but_cannot_be_improved() -> None:
    catalog = ActionCatalog(
        [make_action(action_id="describe_image", input_mode="clipboard_image", with_long_variant=False)]
    )

    summary = RecipeImprovementEvidenceService(catalog, MemoryFeedbackHistory(())).overview().variants[0]

    assert summary.action_id == "describe_image"
    assert summary.improvement_supported is False
    assert summary.unavailable_reason == "目前僅支援文字 Recipe"


def test_current_evidence_is_newest_first_and_exposes_saved_case_without_mutation() -> None:
    catalog = ActionCatalog([make_action(with_long_variant=False)])
    version = catalog.resolve("rewrite", "short").version_id
    older = feedback("1", version=version)
    newer = feedback("2", version=version, outcome="helpful")
    service = RecipeImprovementEvidenceService(
        catalog,
        MemoryFeedbackHistory((older, newer)),
    )

    items = service.evidence("rewrite", "short")

    assert [item.feedback_id for item in items] == ["2", "1"]
    assert items[0].has_saved_case is True
    assert items[0].input_text == "Original"
    assert items[0].result_text == "Result"
    assert service.action("rewrite", "short").version_id == version
