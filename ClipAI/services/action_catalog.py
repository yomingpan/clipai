from __future__ import annotations

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
        return ResolvedAction(
            id=action.id,
            name=variant.name if variant else action.name,
            system_prompt=variant.system_prompt if variant else action.system_prompt,
            prompt=variant.prompt if variant else action.prompt,
            press_type=press_type,
            input_mode=action.input_mode,
            output_mode=action.output_mode,
            temperature=action.temperature,
        )

    def hotkey_action_map(self) -> dict[str, dict[str, str]]:
        return {
            action.id: {"hotkey": action.hotkey}
            for action in self._actions.values()
            if action.hotkey.strip()
        }

