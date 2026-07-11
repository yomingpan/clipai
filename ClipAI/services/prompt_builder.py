from __future__ import annotations

from ClipAI.core.models import LLMMessage, LLMRequest, ResolvedAction
from ClipAI.services.output_profiles import OutputProfileCatalog


class PromptBuilder:
    def __init__(self, default_system_prompt: str = "", output_profiles: OutputProfileCatalog | None = None) -> None:
        self._default_system_prompt = default_system_prompt.strip()
        self._output_profiles = output_profiles or OutputProfileCatalog([])

    def build(self, action: ResolvedAction, input_text: str, *, model: str, default_temperature: float) -> LLMRequest:
        try:
            user_prompt = action.prompt.format(input=input_text)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"invalid prompt template for action {action.id}: {exc}") from exc
        return LLMRequest(
            messages=(
                LLMMessage(role="system", content=self._system_prompt(action.system_prompt, action.output_profile)),
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
                LLMMessage(role="system", content=self._system_prompt(action.system_prompt, action.output_profile)),
                LLMMessage(role="user", content=action.prompt.format(input=original_input)),
                LLMMessage(role="assistant", content=previous_result),
                LLMMessage(role="user", content=question),
            ),
            model=model,
            temperature=action.temperature if action.temperature is not None else default_temperature,
        )

    def _system_prompt(self, action_system_prompt: str, output_profile: str) -> str:
        parts = [self._default_system_prompt, action_system_prompt, self._output_profiles.get(output_profile).instruction]
        return "\n\n".join(part for part in parts if part.strip())
