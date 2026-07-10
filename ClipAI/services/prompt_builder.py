from __future__ import annotations

from ClipAI.core.models import LLMMessage, LLMRequest, ResolvedAction


class PromptBuilder:
    def build(self, action: ResolvedAction, input_text: str, *, model: str, default_temperature: float) -> LLMRequest:
        try:
            user_prompt = action.prompt.format(input=input_text)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"invalid prompt template for action {action.id}: {exc}") from exc
        return LLMRequest(
            messages=(
                LLMMessage(role="system", content=action.system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ),
            model=model,
            temperature=action.temperature if action.temperature is not None else default_temperature,
        )

    def build_follow_up(
        self,
        action: ResolvedAction,
        *,
        original_input: str,
        previous_result: str,
        question: str,
        model: str,
        default_temperature: float,
    ) -> LLMRequest:
        return LLMRequest(
            messages=(
                LLMMessage(role="system", content=action.system_prompt),
                LLMMessage(role="user", content=action.prompt.format(input=original_input)),
                LLMMessage(role="assistant", content=previous_result),
                LLMMessage(role="user", content=question),
            ),
            model=model,
            temperature=action.temperature if action.temperature is not None else default_temperature,
        )
