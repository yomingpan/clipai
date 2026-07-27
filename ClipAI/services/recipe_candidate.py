from __future__ import annotations

import json
from string import Formatter

from ClipAI.core.models import (
    ActionFeedbackRecord,
    LLMMessage,
    LLMRequest,
    LLMResult,
    RecipeCandidateProposal,
    RecipePromptCandidate,
    ResolvedAction,
)


_MAX_PROMPT_CHARS = 20_000
_PROMPT_FIELDS = {
    "classification",
    "explanation_zh_tw",
    "problem_summary_zh_tw",
    "proposed_change_zh_tw",
    "preserve_behavior_zh_tw",
    "system_prompt",
    "prompt",
}
_CLASSIFICATION_FIELDS = {"classification", "explanation_zh_tw"}


class RecipeCandidateService:
    def build_request(
        self,
        action: ResolvedAction,
        evidence: tuple[ActionFeedbackRecord, ...],
        *,
        directions: tuple[str, ...],
        user_direction: str,
        model: str,
    ) -> LLMRequest:
        selected_evidence = [
            {
                "feedback_id": record.feedback_id,
                "outcome": record.outcome,
                "reason": record.reason,
                "note": record.note,
                "input": record.input_text,
                "result": record.result_text,
                "provider": record.provider,
                "model": record.model,
            }
            for record in evidence
        ]
        payload = {
            "recipe": {
                "id": action.id,
                "press_type": action.press_type,
                "system_prompt": action.system_prompt,
                "prompt": action.prompt,
            },
            "selected_evidence": selected_evidence,
            "directions": list(directions),
            "user_direction": user_direction.strip(),
            "allowed_changes": ["system_prompt", "prompt"],
        }
        system = (
            "你是 ClipAI Recipe 改善器。只改善原 Recipe 的 system_prompt 與 prompt，"
            "不得改變用途或任何執行設定。判斷證據若較像 UI／App 問題，classification "
            "設為 app_issue；若證據不足或互相衝突，設為 insufficient_evidence。"
            "否則設為 prompt，並回傳完整 system_prompt、含且只含一次 {input} 的 prompt，"
            "以及繁體中文 problem_summary_zh_tw、proposed_change_zh_tw、"
            "preserve_behavior_zh_tw 與簡短 explanation_zh_tw。只輸出 JSON。"
        )
        return LLMRequest(
            messages=(
                LLMMessage("system", system),
                LLMMessage("user", json.dumps(payload, ensure_ascii=False)),
            ),
            model=model,
            temperature=0.1,
        )

    def parse_proposal(
        self,
        action: ResolvedAction,
        result: LLMResult,
        *,
        iteration: int,
    ) -> RecipeCandidateProposal:
        payload = self._parse_json(result.text)
        classification = payload.get("classification")
        if classification not in {"prompt", "app_issue", "insufficient_evidence"}:
            raise ValueError("unsupported candidate classification")
        explanation = payload.get("explanation_zh_tw")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("candidate explanation is required")
        if classification != "prompt":
            unexpected = set(payload) - _CLASSIFICATION_FIELDS
            if unexpected:
                raise ValueError("unexpected candidate fields")
            return RecipeCandidateProposal(classification, explanation.strip())

        unexpected = set(payload) - _PROMPT_FIELDS
        if unexpected:
            raise ValueError("unexpected candidate fields")
        system_prompt = payload.get("system_prompt")
        prompt = payload.get("prompt")
        problem_summary = self._required_text(
            payload,
            "problem_summary_zh_tw",
        )
        proposed_change = self._required_text(
            payload,
            "proposed_change_zh_tw",
        )
        preserve_behavior = self._required_text(
            payload,
            "preserve_behavior_zh_tw",
        )
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("candidate system prompt is required")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("candidate prompt is required")
        self._validate_template(prompt)
        if len(system_prompt) > _MAX_PROMPT_CHARS or len(prompt) > _MAX_PROMPT_CHARS:
            raise ValueError("candidate prompt exceeds the safe size limit")
        candidate = RecipePromptCandidate(
            action_id=action.id,
            press_type=action.press_type,
            parent_version=action.version_id,
            iteration=iteration,
            system_prompt=system_prompt.strip(),
            prompt=prompt.strip(),
            explanation=explanation.strip(),
            provider=result.provider,
            model=result.model,
            problem_summary=problem_summary,
            proposed_change=proposed_change,
            preserve_behavior=preserve_behavior,
        )
        return RecipeCandidateProposal("prompt", explanation.strip(), candidate)

    def parse_candidate(
        self,
        action: ResolvedAction,
        result: LLMResult,
        *,
        iteration: int,
    ) -> RecipePromptCandidate:
        proposal = self.parse_proposal(action, result, iteration=iteration)
        if proposal.candidate is None:
            raise ValueError("provider did not return a prompt candidate")
        return proposal.candidate

    @staticmethod
    def _required_text(payload: dict[str, object], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"candidate {field} is required")
        return value.strip()

    @staticmethod
    def _validate_template(prompt: str) -> None:
        try:
            fields = [
                field_name
                for _, field_name, _, _ in Formatter().parse(prompt)
                if field_name is not None
            ]
        except ValueError as exc:
            raise ValueError("invalid prompt template") from exc
        if any(field != "input" for field in fields):
            raise ValueError("prompt contains an unsupported template variable")
        if fields.count("input") != 1:
            raise ValueError("prompt must contain {input} exactly once")
        try:
            prompt.format(input="test")
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid prompt template") from exc

    @staticmethod
    def _parse_json(text: str) -> dict[str, object]:
        cleaned = text.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned[3:-3].strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError("provider returned invalid candidate JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("provider returned invalid candidate JSON")
        return payload
