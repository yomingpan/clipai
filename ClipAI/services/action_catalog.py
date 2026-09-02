from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from ClipAI.core.models import ActionDefinition, ActionVersionContext, PressType, ResolvedAction


class ActionCatalog:
    def __init__(
        self,
        actions: list[ActionDefinition],
        *,
        default_stream: bool = False,
        version_context: ActionVersionContext | None = None,
    ) -> None:
        self._actions = {action.id: action for action in actions}
        self._default_stream = default_stream
        self._version_context = version_context
        self._version_profiles = (
            {profile.id: profile for profile in version_context.output_profiles}
            if version_context is not None
            else {}
        )
        if len(self._actions) != len(actions):
            raise ValueError("action ids must be unique")
        if version_context is not None and len(self._version_profiles) != len(
            version_context.output_profiles
        ):
            raise ValueError("action version profile ids must be unique")

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
            feedback_contract=(variant.feedback_contract if variant and variant.feedback_contract is not None else action.feedback_contract),
            stream=self._default_stream if action.stream is None else action.stream,
            personal_style_mode=action.personal_style_mode,
            action_language=(
                self._version_context.provenance
                if self._version_context is not None
                else None
            ),
        )
        version_payload = {
            "id": resolved.id,
            "name": resolved.name,
            "press_type": resolved.press_type,
            "system_prompt": resolved.system_prompt,
            "prompt": resolved.prompt,
            "input_mode": resolved.input_mode,
            "output_mode": resolved.output_mode,
            "temperature": resolved.temperature,
            "output_profile": resolved.output_profile,
            "external_fallback": resolved.external_fallback,
            "feedback_contract": None if resolved.feedback_contract is None else {
                "helps": resolved.feedback_contract.ai_help_label,
                "does_not": resolved.feedback_contract.ai_does_not_label,
                "reasons": [(reason.id, reason.label) for reason in resolved.feedback_contract.reasons],
            },
            "stream": resolved.stream,
            "personal_style_mode": resolved.personal_style_mode,
        }
        if self._version_context is not None:
            try:
                profile = self._version_profiles[resolved.output_profile]
            except KeyError as exc:
                raise ValueError(
                    f"action {resolved.id} references unknown version profile: "
                    f"{resolved.output_profile}"
                ) from exc
            identity = self._version_context.provenance.identity
            version_payload["output_profile_resource"] = {
                "id": profile.id,
                "instruction": profile.instruction,
                "required_markers": profile.required_markers,
                "presentation": profile.presentation,
            }
            version_payload["action_language"] = {
                "pack_id": identity.pack_id,
                "pack_version": identity.pack_version,
                "locale": identity.locale,
                "feature_contract_hash": self._version_context.provenance.feature_contract_hash,
                "resource_content_hash": self._version_context.provenance.resource_content_hash,
            }
        version_id = hashlib.sha256(json.dumps(version_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return replace(resolved, version_id=version_id)

    def contains(self, action_id: str) -> bool:
        return action_id in self._actions
