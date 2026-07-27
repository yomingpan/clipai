from __future__ import annotations

from ClipAI.core.models import (
    ActionFeedbackRecord,
    PressType,
    RecipeEvidenceItem,
    RecipeImprovementOverview,
    RecipeVariantSummary,
    ResolvedAction,
)
from ClipAI.core.ports import ActionFeedbackHistory
from ClipAI.services.action_catalog import ActionCatalog


class RecipeImprovementEvidenceService:
    def __init__(
        self,
        actions: ActionCatalog,
        feedback_history: ActionFeedbackHistory,
    ) -> None:
        self._actions = actions
        self._feedback_history = feedback_history

    def overview(self) -> RecipeImprovementOverview:
        records = self._feedback_history.load()
        variants: list[RecipeVariantSummary] = []
        for action in self._actions.resolved_variants():
            current_records = tuple(
                record
                for record in records
                if record.action_id == action.id
                and record.press_type == action.press_type
                and record.action_version == action.version_id
            )
            saved_cases = tuple(
                record
                for record in current_records
                if record.input_text is not None and record.result_text is not None
            )
            negative_count = sum(
                record.outcome == "needs_adjustment" for record in current_records
            )
            helpful_count = sum(record.outcome == "helpful" for record in current_records)
            supported = action.input_mode != "clipboard_image"
            variants.append(
                RecipeVariantSummary(
                    action_id=action.id,
                    name=action.name,
                    press_type=action.press_type,
                    current_version=action.version_id,
                    feedback_count=len(current_records),
                    saved_case_count=len(saved_cases),
                    negative_feedback_count=negative_count,
                    helpful_feedback_count=helpful_count,
                    reminder_recommended=negative_count >= 1 and len(saved_cases) >= 3,
                    improvement_supported=supported,
                    unavailable_reason="" if supported else "目前僅支援文字 Recipe",
                )
            )
        return RecipeImprovementOverview(tuple(variants))

    def action(self, action_id: str, press_type: PressType) -> ResolvedAction:
        return self._actions.resolve(action_id, press_type)

    def evidence(
        self,
        action_id: str,
        press_type: PressType,
    ) -> tuple[RecipeEvidenceItem, ...]:
        action = self.action(action_id, press_type)
        records = sorted(
            (
                record
                for record in self._feedback_history.load()
                if record.action_id == action_id
                and record.press_type == press_type
                and record.action_version == action.version_id
            ),
            key=lambda record: record.created_at,
            reverse=True,
        )
        return tuple(
            RecipeEvidenceItem(
                feedback_id=record.feedback_id,
                created_at=record.created_at,
                outcome=record.outcome,
                reason=record.reason,
                note=record.note,
                provider=record.provider,
                model=record.model,
                has_saved_case=record.input_text is not None
                and record.result_text is not None,
                input_text=record.input_text,
                result_text=record.result_text,
            )
            for record in records
        )

    def selected_records(
        self,
        action_id: str,
        press_type: PressType,
        feedback_ids: tuple[str, ...],
    ) -> tuple[ActionFeedbackRecord, ...]:
        selected = set(feedback_ids)
        action = self.action(action_id, press_type)
        records = tuple(
            record
            for record in self._feedback_history.load()
            if record.action_id == action_id
            and record.press_type == press_type
            and record.action_version == action.version_id
            and record.feedback_id in selected
        )
        if len(records) != len(selected):
            raise ValueError("selected feedback is no longer available")
        return records
