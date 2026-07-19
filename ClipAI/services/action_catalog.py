from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from ClipAI.core.models import ActionDefinition, PressType, ResolvedAction


class ActionCatalog:
    def __init__(self, actions: list[ActionDefinition]) -> None:
        self._actions = {action.id: action for action in actions}
        if len(self._actions) != len(actions):
            raise ValueError("action ids must be unique")

    def get(self, action_id: str) -> ActionDefinition:
        try:
            return self._actions[action_id]
        except KeyError as exc:
            raise ValueError(f"unknown action: {action_id}") from exc

    def resolve(self, action_id: str, press_type: PressType) -> ResolvedAction:
        action = self.get(action_id)
        variant = action.press_variants.get(press_type)
        resolved = ResolvedAction(
            id=action.id,
            name=variant.name if variant else action.name,
            system_prompt=variant.system_prompt if variant else action.system_prompt,
            prompt=variant.prompt if variant else action.prompt,
            press_type=press_type,
            input_mode=action.input_mode,
            output_mode=action.output_mode,
            temperature=action.temperature,
            output_profile=variant.output_profile if variant and variant.output_profile else action.output_profile,
            external_fallback=action.external_fallback,
            feedback_contract=action.feedback_contract,
        )
        version_payload = {
            "id": resolved.id,
            "press_type": resolved.press_type,
            "system_prompt": resolved.system_prompt,
            "prompt": resolved.prompt,
            "input_mode": resolved.input_mode,
            "output_mode": resolved.output_mode,
            "temperature": resolved.temperature,
            "output_profile": resolved.output_profile,
            "external_fallback": resolved.external_fallback,
            "feedback_contract": None if resolved.feedback_contract is None else {
                "transform": resolved.feedback_contract.transform_label,
                "human_space": resolved.feedback_contract.human_space_label,
                "reasons": [(reason.id, reason.label) for reason in resolved.feedback_contract.reasons],
            },
        }
        version_id = hashlib.sha256(json.dumps(version_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return replace(resolved, version_id=version_id)

    def contains(self, action_id: str) -> bool:
        return action_id in self._actions
