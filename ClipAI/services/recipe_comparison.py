from __future__ import annotations

from ClipAI.core.models import ActionFeedbackRecord, RecipeApplyGate


class RecipeComparisonPolicy:
    def default_feedback_ids(
        self,
        records: tuple[ActionFeedbackRecord, ...],
    ) -> tuple[str, ...]:
        saved = tuple(
            record
            for record in records
            if record.input_text is not None and record.result_text is not None
        )
        negatives = sorted(
            (record for record in saved if record.outcome == "needs_adjustment"),
            key=lambda record: record.created_at,
            reverse=True,
        )
        helpful = sorted(
            (record for record in saved if record.outcome == "helpful"),
            key=lambda record: record.created_at,
            reverse=True,
        )
        selected = negatives[:2]
        if helpful:
            selected.append(helpful[0])
        else:
            selected = negatives[:3]
        return tuple(record.feedback_id for record in selected)

    @staticmethod
    def validate_test_count(count: int) -> None:
        if not 1 <= count <= 5:
            raise ValueError("choose between 1 and 5 test cases")

    @staticmethod
    def apply_gate(verdicts: tuple[str, ...]) -> RecipeApplyGate:
        if not verdicts:
            return RecipeApplyGate("blocked", "至少需要一個成功的比較結果。")
        if "both_need_work" in verdicts:
            return RecipeApplyGate("blocked", "候選仍需改善，請先產生下一版。")
        candidate_wins = verdicts.count("candidate_better")
        current_wins = verdicts.count("current_better")
        if candidate_wins == len(verdicts):
            return RecipeApplyGate("direct", "所有比較都偏好新版本。")
        if candidate_wins and current_wins:
            return RecipeApplyGate("confirm", "比較結果不一致，套用前需要再次確認。")
        return RecipeApplyGate("blocked", "目前版本在比較中較好，不能套用此候選。")
