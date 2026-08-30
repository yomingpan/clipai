from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from string import Formatter
from typing import Literal, TypeVar

from ClipAI.core.errors import ActionLanguagePackError, ActionLanguagePackErrorCode
from ClipAI.core.models import (
    ActionDefinition,
    ActionFeedbackContract,
    ActionLanguagePackDescriptor,
    ActionLanguagePackIdentity,
    ActionLanguageProvenance,
    ActionVariant,
    ExternalFallback,
    FeedbackReason,
    InputMode,
    OutputMode,
    OutputProfile,
    PersonalStyleMode,
    PressType,
    ShortcutDefinition,
)


MarkerKind = Literal["localized", "control_token"]
SUPPORTED_MANIFEST_SCHEMA_VERSION = 1
FEATURE_CONTRACT_VERSION = 1
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
T = TypeVar("T")


@dataclass(frozen=True)
class ActionVariantSkeleton:
    press_type: PressType
    output_profile: str | None = None
    prompt_variables: tuple[str, ...] = ("input",)
    feedback_reason_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ActionSkeleton:
    id: str
    stream: bool | None = None
    input_mode: InputMode = "selection_or_clipboard"
    output_mode: OutputMode = "popup"
    temperature: float | None = None
    output_profile: str = "plain_text"
    external_fallback: ExternalFallback = "selection_or_clipboard"
    personal_style_mode: PersonalStyleMode | None = None
    prompt_variables: tuple[str, ...] = ("input",)
    feedback_reason_ids: tuple[str, ...] | None = None
    variants: tuple[ActionVariantSkeleton, ...] = ()


@dataclass(frozen=True)
class OutputMarkerSkeleton:
    marker_id: str
    kind: MarkerKind
    literal: str = ""


@dataclass(frozen=True)
class OutputProfileSkeleton:
    id: str
    presentation: str
    markers: tuple[OutputMarkerSkeleton, ...] = ()


@dataclass(frozen=True)
class FeatureSkeleton:
    actions: tuple[ActionSkeleton, ...]
    shortcuts: tuple[ShortcutDefinition, ...]
    output_profiles: tuple[OutputProfileSkeleton, ...]
    contract_version: int = FEATURE_CONTRACT_VERSION


@dataclass(frozen=True)
class ActionLanguagePackManifest:
    schema_version: int
    pack_id: str
    locale: str
    display_name: str
    pack_version: str
    feature_contract_hash: str

    @property
    def identity(self) -> ActionLanguagePackIdentity:
        return ActionLanguagePackIdentity(
            pack_id=self.pack_id,
            pack_version=self.pack_version,
            locale=self.locale,
        )


@dataclass(frozen=True)
class LocalizedFeedback:
    helps: str
    does_not: str
    reasons: tuple[FeedbackReason, ...]


@dataclass(frozen=True)
class LocalizedActionVariant:
    press_type: PressType
    name: str
    system_prompt: str
    prompt: str
    feedback: LocalizedFeedback | None = None


@dataclass(frozen=True)
class LocalizedAction:
    id: str
    name: str
    system_prompt: str
    prompt: str
    feedback: LocalizedFeedback | None = None
    variants: tuple[LocalizedActionVariant, ...] = ()


@dataclass(frozen=True)
class LocalizedMarker:
    marker_id: str
    literal: str


@dataclass(frozen=True)
class LocalizedOutputProfile:
    id: str
    instruction: str
    markers: tuple[LocalizedMarker, ...] = ()


@dataclass(frozen=True)
class ActionLanguageResources:
    default_system_prompt: str
    actions: tuple[LocalizedAction, ...]
    output_profiles: tuple[LocalizedOutputProfile, ...]


@dataclass(frozen=True)
class CompiledActionLanguagePack:
    descriptor: ActionLanguagePackDescriptor
    provenance: ActionLanguageProvenance
    default_system_prompt: str
    action_definitions: tuple[ActionDefinition, ...]
    output_profiles: tuple[OutputProfile, ...]


def feature_contract_hash(skeleton: FeatureSkeleton) -> str:
    """Hash every non-localizable feature contract in deterministic order."""

    payload = {
        "contract_version": skeleton.contract_version,
        "actions": [
            {
                "id": action.id,
                "stream": action.stream,
                "input_mode": action.input_mode,
                "output_mode": action.output_mode,
                "temperature": action.temperature,
                "output_profile": action.output_profile,
                "external_fallback": action.external_fallback,
                "personal_style_mode": action.personal_style_mode,
                "prompt_variables": list(action.prompt_variables),
                "feedback_reason_ids": _optional_list(action.feedback_reason_ids),
                "variants": [
                    {
                        "press_type": variant.press_type,
                        "output_profile": variant.output_profile,
                        "prompt_variables": list(variant.prompt_variables),
                        "feedback_reason_ids": _optional_list(
                            variant.feedback_reason_ids
                        ),
                    }
                    for variant in action.variants
                ],
            }
            for action in skeleton.actions
        ],
        "shortcuts": [
            {
                "id": shortcut.id,
                "hotkey": shortcut.hotkey,
                "command": shortcut.command,
                "action_id": shortcut.action_id,
            }
            for shortcut in skeleton.shortcuts
        ],
        "output_profiles": [
            {
                "id": profile.id,
                "presentation": profile.presentation,
                "markers": [
                    {
                        "marker_id": marker.marker_id,
                        "kind": marker.kind,
                        "literal": marker.literal
                        if marker.kind == "control_token"
                        else None,
                    }
                    for marker in profile.markers
                ],
            }
            for profile in skeleton.output_profiles
        ],
    }
    return _hash_payload(payload)


def compile_pack(
    skeleton: FeatureSkeleton,
    manifest: ActionLanguagePackManifest,
    resources: ActionLanguageResources,
) -> CompiledActionLanguagePack:
    """Compile one complete language pack or fail without a partial result."""

    _validate_manifest(manifest)
    _validate_skeleton(skeleton)
    contract_hash = feature_contract_hash(skeleton)
    if manifest.feature_contract_hash != contract_hash:
        _fail(
            "contract_mismatch",
            "manifest.feature_contract_hash",
            "language pack does not match the canonical feature contract",
        )

    _validate_plain_text(
        resources.default_system_prompt,
        "resources.app.default_system_prompt",
        allow_empty=False,
    )
    localized_actions = _exact_index(
        resources.actions,
        expected=tuple(action.id for action in skeleton.actions),
        path="resources.actions",
        reason="inventory_mismatch",
    )
    localized_profiles = _exact_index(
        resources.output_profiles,
        expected=tuple(profile.id for profile in skeleton.output_profiles),
        path="resources.output_profiles",
        reason="inventory_mismatch",
    )

    definitions = tuple(
        _compile_action(action, localized_actions[action.id])
        for action in skeleton.actions
    )
    profiles = tuple(
        _compile_profile(profile, localized_profiles[profile.id])
        for profile in skeleton.output_profiles
    )
    profile_ids = {profile.id for profile in profiles}
    for action in definitions:
        referenced = {
            action.output_profile,
            *(
                variant.output_profile
                for variant in action.press_variants.values()
                if variant.output_profile is not None
            ),
        }
        unknown = referenced - profile_ids
        if unknown:
            _fail(
                "contract_mismatch",
                f"skeleton.actions.{action.id}.output_profile",
                "action references an unknown output profile",
            )

    resource_hash = _resource_content_hash(resources)
    provenance = ActionLanguageProvenance(
        identity=manifest.identity,
        feature_contract_hash=contract_hash,
        resource_content_hash=resource_hash,
    )
    return CompiledActionLanguagePack(
        descriptor=ActionLanguagePackDescriptor(
            identity=manifest.identity,
            display_name=manifest.display_name,
        ),
        provenance=provenance,
        default_system_prompt=resources.default_system_prompt,
        action_definitions=definitions,
        output_profiles=profiles,
    )


def _compile_action(
    skeleton: ActionSkeleton,
    localized: LocalizedAction,
) -> ActionDefinition:
    path = f"resources.actions.{skeleton.id}"
    _validate_localized_text(localized.name, f"{path}.name")
    _validate_plain_text(localized.system_prompt, f"{path}.system_prompt")
    _validate_prompt(localized.prompt, skeleton.prompt_variables, f"{path}.prompt")
    feedback = _compile_feedback(
        localized.feedback,
        skeleton.feedback_reason_ids,
        f"{path}.feedback",
    )

    localized_variants = _exact_index(
        localized.variants,
        expected=tuple(variant.press_type for variant in skeleton.variants),
        path=f"{path}.variants",
        reason="inventory_mismatch",
        key="press_type",
    )
    variants: dict[PressType, ActionVariant] = {}
    for variant in skeleton.variants:
        variant_text = localized_variants[variant.press_type]
        variant_path = f"{path}.variants.{variant.press_type}"
        _validate_localized_text(variant_text.name, f"{variant_path}.name")
        _validate_plain_text(
            variant_text.system_prompt,
            f"{variant_path}.system_prompt",
        )
        _validate_prompt(
            variant_text.prompt,
            variant.prompt_variables,
            f"{variant_path}.prompt",
        )
        variants[variant.press_type] = ActionVariant(
            name=variant_text.name,
            system_prompt=variant_text.system_prompt,
            prompt=variant_text.prompt,
            output_profile=variant.output_profile,
            feedback_contract=_compile_feedback(
                variant_text.feedback,
                variant.feedback_reason_ids,
                f"{variant_path}.feedback",
            ),
        )

    return ActionDefinition(
        id=skeleton.id,
        name=localized.name,
        system_prompt=localized.system_prompt,
        prompt=localized.prompt,
        press_variants=variants,
        stream=skeleton.stream,
        input_mode=skeleton.input_mode,
        output_mode=skeleton.output_mode,
        temperature=skeleton.temperature,
        output_profile=skeleton.output_profile,
        external_fallback=skeleton.external_fallback,
        feedback_contract=feedback,
        personal_style_mode=skeleton.personal_style_mode,
    )


def _compile_feedback(
    localized: LocalizedFeedback | None,
    expected_reason_ids: tuple[str, ...] | None,
    path: str,
) -> ActionFeedbackContract | None:
    if expected_reason_ids is None:
        if localized is not None:
            _fail(
                "feedback_contract_mismatch",
                path,
                "pack provides feedback where the skeleton declares inheritance or absence",
            )
        return None
    if localized is None:
        _fail(
            "feedback_contract_mismatch",
            path,
            "pack is missing a required feedback contract",
        )
    assert localized is not None
    _validate_localized_text(localized.helps, f"{path}.helps")
    _validate_localized_text(localized.does_not, f"{path}.does_not")
    actual_ids = tuple(reason.id for reason in localized.reasons)
    if actual_ids != expected_reason_ids or len(set(actual_ids)) != len(actual_ids):
        _fail(
            "feedback_contract_mismatch",
            f"{path}.reasons",
            "feedback reason ids or order do not match the skeleton",
        )
    for reason in localized.reasons:
        _validate_localized_text(reason.label, f"{path}.reasons.{reason.id}")
    return ActionFeedbackContract(
        ai_help_label=localized.helps,
        ai_does_not_label=localized.does_not,
        reasons=localized.reasons,
    )


def _compile_profile(
    skeleton: OutputProfileSkeleton,
    localized: LocalizedOutputProfile,
) -> OutputProfile:
    path = f"resources.output_profiles.{skeleton.id}"
    _validate_plain_text(
        localized.instruction,
        f"{path}.instruction",
        allow_empty=skeleton.id == "plain_text",
    )
    expected_localized_ids = tuple(
        marker.marker_id
        for marker in skeleton.markers
        if marker.kind == "localized"
    )
    localized_markers = _exact_index(
        localized.markers,
        expected=expected_localized_ids,
        path=f"{path}.markers",
        reason="marker_contract_mismatch",
        key="marker_id",
        ordered=False,
    )
    required_markers: list[str] = []
    for marker in skeleton.markers:
        if marker.kind == "control_token":
            required_markers.append(marker.literal)
            continue
        marker_text = localized_markers[marker.marker_id].literal
        _validate_localized_text(marker_text, f"{path}.markers.{marker.marker_id}")
        required_markers.append(marker_text)
    return OutputProfile(
        id=skeleton.id,
        instruction=localized.instruction,
        required_markers=tuple(required_markers),
        presentation=skeleton.presentation,
    )


def _validate_manifest(manifest: ActionLanguagePackManifest) -> None:
    if manifest.schema_version != SUPPORTED_MANIFEST_SCHEMA_VERSION:
        _fail(
            "manifest_invalid",
            "manifest.schema_version",
            "unsupported language pack manifest schema",
        )
    if not _IDENTIFIER.fullmatch(manifest.pack_id):
        _fail("manifest_invalid", "manifest.pack_id", "invalid pack identifier")
    if not manifest.locale.strip():
        _fail("manifest_invalid", "manifest.locale", "locale must not be empty")
    if not manifest.display_name.strip():
        _fail(
            "manifest_invalid",
            "manifest.display_name",
            "display name must not be empty",
        )
    if not _SEMVER.fullmatch(manifest.pack_version):
        _fail(
            "manifest_invalid",
            "manifest.pack_version",
            "pack version must be SemVer",
        )


def _validate_skeleton(skeleton: FeatureSkeleton) -> None:
    if skeleton.contract_version != FEATURE_CONTRACT_VERSION:
        _fail(
            "contract_mismatch",
            "skeleton.contract_version",
            "unsupported canonical feature contract version",
        )
    _require_unique(
        tuple(action.id for action in skeleton.actions),
        "skeleton.actions",
        "inventory_mismatch",
    )
    _require_unique(
        tuple(profile.id for profile in skeleton.output_profiles),
        "skeleton.output_profiles",
        "inventory_mismatch",
    )
    profile_ids = {profile.id for profile in skeleton.output_profiles}
    if "plain_text" not in profile_ids:
        _fail(
            "inventory_mismatch",
            "skeleton.output_profiles",
            "plain_text must be an explicit canonical profile",
        )
    action_ids = {action.id for action in skeleton.actions}
    for action in skeleton.actions:
        _validate_prompt_variables(
            action.prompt_variables,
            f"skeleton.actions.{action.id}.prompt_variables",
        )
        _validate_reason_ids(
            action.feedback_reason_ids,
            f"skeleton.actions.{action.id}.feedback_reason_ids",
        )
        _require_unique(
            tuple(variant.press_type for variant in action.variants),
            f"skeleton.actions.{action.id}.variants",
            "inventory_mismatch",
        )
        if action.output_profile not in profile_ids:
            _fail(
                "contract_mismatch",
                f"skeleton.actions.{action.id}.output_profile",
                "action references an unknown output profile",
            )
        for variant in action.variants:
            _validate_prompt_variables(
                variant.prompt_variables,
                f"skeleton.actions.{action.id}.variants.{variant.press_type}.prompt_variables",
            )
            _validate_reason_ids(
                variant.feedback_reason_ids,
                f"skeleton.actions.{action.id}.variants.{variant.press_type}.feedback_reason_ids",
            )
            if variant.output_profile and variant.output_profile not in profile_ids:
                _fail(
                    "contract_mismatch",
                    f"skeleton.actions.{action.id}.variants.{variant.press_type}.output_profile",
                    "variant references an unknown output profile",
                )
    _require_unique(
        tuple(shortcut.id for shortcut in skeleton.shortcuts),
        "skeleton.shortcuts",
        "contract_mismatch",
    )
    for shortcut in skeleton.shortcuts:
        if shortcut.command == "start_action" and shortcut.action_id not in action_ids:
            _fail(
                "contract_mismatch",
                f"skeleton.shortcuts.{shortcut.id}.action_id",
                "shortcut references an unknown action",
            )
    for profile in skeleton.output_profiles:
        _require_unique(
            tuple(marker.marker_id for marker in profile.markers),
            f"skeleton.output_profiles.{profile.id}.markers",
            "marker_contract_mismatch",
        )
        for marker in profile.markers:
            if marker.kind == "control_token" and not marker.literal:
                _fail(
                    "marker_contract_mismatch",
                    f"skeleton.output_profiles.{profile.id}.markers.{marker.marker_id}",
                    "control token must have a canonical literal",
                )
            if marker.kind == "localized" and marker.literal:
                _fail(
                    "marker_contract_mismatch",
                    f"skeleton.output_profiles.{profile.id}.markers.{marker.marker_id}",
                    "localized marker literal must come from the language pack",
                )


def _validate_prompt(prompt: str, variables: tuple[str, ...], path: str) -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        _fail("prompt_template_invalid", path, "prompt must not be empty")
    try:
        parsed = tuple(Formatter().parse(prompt))
    except ValueError:
        _fail("prompt_template_invalid", path, "prompt contains malformed braces")
    fields: list[str] = []
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name != "input":
            _fail(
                "prompt_template_invalid",
                path,
                "prompt contains an unsupported template field",
            )
        if conversion is not None or format_spec:
            _fail(
                "prompt_template_invalid",
                path,
                "prompt conversion and format specifiers are forbidden",
            )
        fields.append(field_name)
    if tuple(fields) != variables:
        _fail(
            "prompt_template_invalid",
            path,
            "prompt variables or occurrence count do not match the skeleton",
        )
    try:
        prompt.format(input="sentinel { braces }\n非 ASCII")
    except (IndexError, KeyError, ValueError):
        _fail(
            "prompt_template_invalid",
            path,
            "prompt failed deterministic render smoke",
        )


def _validate_plain_text(
    value: str,
    path: str,
    *,
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail("inventory_mismatch", path, "required localized text is empty")
    if "{" in value or "}" in value:
        _fail(
            "prompt_template_invalid",
            path,
            "non-template text must not contain placeholder braces",
        )


def _validate_localized_text(value: str, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail("inventory_mismatch", path, "required localized text is empty")


def _validate_prompt_variables(variables: tuple[str, ...], path: str) -> None:
    if variables != ("input",):
        _fail(
            "contract_mismatch",
            path,
            "Phase 1 supports exactly one input prompt variable",
        )


def _validate_reason_ids(reason_ids: tuple[str, ...] | None, path: str) -> None:
    if reason_ids is None:
        return
    if not reason_ids or len(set(reason_ids)) != len(reason_ids):
        _fail(
            "feedback_contract_mismatch",
            path,
            "feedback reason ids must be non-empty and unique",
        )


def _exact_index(
    values: tuple[T, ...],
    *,
    expected: tuple[str, ...],
    path: str,
    reason: ActionLanguagePackErrorCode,
    key: str = "id",
    ordered: bool = False,
) -> dict[str, T]:
    actual = tuple(getattr(value, key) for value in values)
    if len(set(actual)) != len(actual):
        _fail(reason, path, "resource contains duplicate identifiers")
    matches = actual == expected if ordered else set(actual) == set(expected)
    if not matches:
        _fail(reason, path, "resource inventory does not match the skeleton")
    return {getattr(value, key): value for value in values}


def _require_unique(
    values: tuple[str, ...],
    path: str,
    reason: ActionLanguagePackErrorCode,
) -> None:
    if len(set(values)) != len(values):
        _fail(reason, path, "canonical identifiers must be unique")


def _resource_content_hash(resources: ActionLanguageResources) -> str:
    payload = {
        "default_system_prompt": resources.default_system_prompt,
        "actions": [
            {
                "id": action.id,
                "name": action.name,
                "system_prompt": action.system_prompt,
                "prompt": action.prompt,
                "feedback": _feedback_payload(action.feedback),
                "variants": [
                    {
                        "press_type": variant.press_type,
                        "name": variant.name,
                        "system_prompt": variant.system_prompt,
                        "prompt": variant.prompt,
                        "feedback": _feedback_payload(variant.feedback),
                    }
                    for variant in sorted(
                        action.variants,
                        key=lambda item: item.press_type,
                    )
                ],
            }
            for action in sorted(resources.actions, key=lambda item: item.id)
        ],
        "output_profiles": [
            {
                "id": profile.id,
                "instruction": profile.instruction,
                "markers": [
                    {"marker_id": marker.marker_id, "literal": marker.literal}
                    for marker in sorted(
                        profile.markers,
                        key=lambda item: item.marker_id,
                    )
                ],
            }
            for profile in sorted(
                resources.output_profiles,
                key=lambda item: item.id,
            )
        ],
    }
    return _hash_payload(payload)


def _feedback_payload(feedback: LocalizedFeedback | None) -> object:
    if feedback is None:
        return None
    return {
        "helps": feedback.helps,
        "does_not": feedback.does_not,
        "reasons": [
            {"id": reason.id, "label": reason.label}
            for reason in feedback.reasons
        ],
    }


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _optional_list(value: tuple[str, ...] | None) -> list[str] | None:
    return None if value is None else list(value)


def _fail(
    reason: ActionLanguagePackErrorCode,
    path: str,
    message: str,
) -> None:
    raise ActionLanguagePackError(reason, path, f"{path}: {message}")
