from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import yaml

from ClipAI.app.config_yaml import UniqueKeyLoader
from ClipAI.core.errors import ActionLanguagePackError, ActionLanguagePackErrorCode
from ClipAI.core.models import (
    ExternalFallback,
    FeedbackReason,
    InputMode,
    OutputMode,
    PersonalStyleMode,
    PressType,
    ShortcutCommandKind,
    ShortcutDefinition,
)
from ClipAI.services.action_language_packs import (
    ActionLanguagePackManifest,
    ActionLanguageResources,
    ActionSkeleton,
    ActionVariantSkeleton,
    CompiledActionLanguagePack,
    EntryPanelCandidateSkeleton,
    EntryPanelCategorySkeleton,
    FeatureSkeleton,
    LocalizedAction,
    LocalizedActionVariant,
    LocalizedEntryPanelCandidate,
    LocalizedFeedback,
    LocalizedMarker,
    LocalizedOutputProfile,
    OutputMarkerSkeleton,
    OutputProfileSkeleton,
    compile_pack,
)


MAX_LANGUAGE_PACK_FILE_BYTES = 2 * 1024 * 1024
LANGUAGE_PACK_REGISTRY_SCHEMA_VERSION = 1
ACTION_SKELETON_SCHEMA_VERSION = 11
OUTPUT_PROFILE_SKELETON_SCHEMA_VERSION = 2
ENTRY_PANEL_SKELETON_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class LanguagePackRegistryEntry:
    pack_id: str
    path: str


@dataclass(frozen=True)
class ActionLanguagePackRegistry:
    default_pack_id: str
    packs: tuple[LanguagePackRegistryEntry, ...]

    def entry(self, pack_id: str) -> LanguagePackRegistryEntry:
        for entry in self.packs:
            if entry.pack_id == pack_id:
                return entry
        _fail("pack_missing", "registry.packs", "pack is not in the official registry")


@dataclass(frozen=True)
class _ResourceReference:
    path: str
    sha256: str


@dataclass(frozen=True)
class _ParsedManifest:
    manifest: ActionLanguagePackManifest
    resources: dict[str, _ResourceReference]


class ActionLanguagePackLoader:
    """Filesystem adapter for strict official language-pack loading."""

    def __init__(self, config_dir: str | Path, skeleton: FeatureSkeleton) -> None:
        self._config_dir = Path(config_dir).resolve()
        self._skeleton = skeleton

    def load_registry(self) -> ActionLanguagePackRegistry:
        path = self._config_dir / "language_packs.yaml"
        payload = _read_yaml(path, reason="registry_invalid")
        _schema(payload, LANGUAGE_PACK_REGISTRY_SCHEMA_VERSION, "registry")
        _reject_unknown(
            payload,
            {"schema_version", "default_pack_id", "packs"},
            "registry",
            "registry_invalid",
        )
        default_pack_id = _text(
            payload.get("default_pack_id"),
            "registry.default_pack_id",
            "registry_invalid",
        )
        raw_packs = _list(payload.get("packs"), "registry.packs", "registry_invalid")
        entries: list[LanguagePackRegistryEntry] = []
        for index, raw_entry in enumerate(raw_packs):
            entry_path = f"registry.packs[{index}]"
            data = _mapping(raw_entry, entry_path, "registry_invalid")
            _reject_unknown(
                data,
                {"pack_id", "path"},
                entry_path,
                "registry_invalid",
            )
            pack_id = _text(data.get("pack_id"), f"{entry_path}.pack_id", "registry_invalid")
            relative = _text(data.get("path"), f"{entry_path}.path", "registry_invalid")
            _resolve_contained(self._config_dir, relative, f"{entry_path}.path", "registry_invalid")
            entries.append(LanguagePackRegistryEntry(pack_id, relative))
        pack_ids = tuple(entry.pack_id for entry in entries)
        if len(set(pack_ids)) != len(pack_ids):
            _fail("registry_invalid", "registry.packs", "duplicate pack id")
        if default_pack_id not in pack_ids:
            _fail(
                "registry_invalid",
                "registry.default_pack_id",
                "default pack is not registered",
            )
        return ActionLanguagePackRegistry(default_pack_id, tuple(entries))

    def load(self, entry: LanguagePackRegistryEntry) -> CompiledActionLanguagePack:
        pack_root = _resolve_contained(
            self._config_dir,
            entry.path,
            f"registry.packs.{entry.pack_id}.path",
            "resource_path_invalid",
        )
        if pack_root.name != entry.pack_id:
            _fail(
                "manifest_invalid",
                "manifest.pack_id",
                "registry path identity does not match pack id",
            )
        parsed = _parse_manifest(pack_root / "manifest.yaml")
        manifest = parsed.manifest
        if manifest.pack_id != entry.pack_id:
            _fail(
                "manifest_invalid",
                "manifest.pack_id",
                "manifest identity does not match registry entry",
            )
        payloads = {
            name: _read_verified_resource(pack_root, name, reference)
            for name, reference in parsed.resources.items()
        }
        resources = _parse_resources(payloads)
        return compile_pack(self._skeleton, manifest, resources)


def load_feature_skeleton(
    config_dir: str | Path,
    *,
    actions_path: str | Path | None = None,
    shortcuts_path: str | Path | None = None,
    output_profiles_path: str | Path | None = None,
    entry_panel_path: str | Path | None = None,
) -> FeatureSkeleton:
    root = Path(config_dir)
    actions = _parse_action_skeleton(Path(actions_path) if actions_path is not None else root / "actions.yaml")
    shortcuts = _parse_shortcut_skeleton(Path(shortcuts_path) if shortcuts_path is not None else root / "shortcuts.yaml")
    profiles = _parse_output_profile_skeleton(
        Path(output_profiles_path)
        if output_profiles_path is not None
        else root / "output_profiles.yaml"
    )
    entry_panel_categories = _parse_entry_panel_skeleton(
        Path(entry_panel_path)
        if entry_panel_path is not None
        else root / "entry_panel.yaml"
    )
    return FeatureSkeleton(
        actions=actions,
        shortcuts=shortcuts,
        output_profiles=profiles,
        entry_panel_categories=entry_panel_categories,
    )


def validate_official_language_packs(
    config_dir: str | Path = "config",
) -> tuple[CompiledActionLanguagePack, ...]:
    skeleton = load_feature_skeleton(config_dir)
    loader = ActionLanguagePackLoader(config_dir, skeleton)
    registry = loader.load_registry()
    return tuple(loader.load(entry) for entry in registry.packs)


def _parse_manifest(path: Path) -> _ParsedManifest:
    payload = _read_yaml(
        path,
        reason="manifest_invalid",
        missing_reason="pack_missing",
    )
    _schema(payload, 1, "manifest")
    _reject_unknown(
        payload,
        {
            "schema_version",
            "pack_id",
            "locale",
            "display_name",
            "pack_version",
            "feature_contract_hash",
            "resources",
        },
        "manifest",
        "manifest_invalid",
    )
    resources = _mapping(payload.get("resources"), "manifest.resources", "manifest_invalid")
    required = {"app", "actions", "output_profiles", "entry_panel"}
    if set(resources) != required:
        _fail(
            "manifest_invalid",
            "manifest.resources",
            "manifest must declare exactly the supported resources",
        )
    references: dict[str, _ResourceReference] = {}
    for name in ("app", "actions", "output_profiles", "entry_panel"):
        resource_path = f"manifest.resources.{name}"
        data = _mapping(resources[name], resource_path, "manifest_invalid")
        _reject_unknown(data, {"path", "sha256"}, resource_path, "manifest_invalid")
        checksum = _text(data.get("sha256"), f"{resource_path}.sha256", "manifest_invalid")
        if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
            _fail(
                "manifest_invalid",
                f"{resource_path}.sha256",
                "checksum must be a lowercase SHA-256 digest",
            )
        references[name] = _ResourceReference(
            path=_text(data.get("path"), f"{resource_path}.path", "manifest_invalid"),
            sha256=checksum,
        )
    manifest = ActionLanguagePackManifest(
        schema_version=_integer(payload.get("schema_version"), "manifest.schema_version", "manifest_invalid"),
        pack_id=_text(payload.get("pack_id"), "manifest.pack_id", "manifest_invalid"),
        locale=_text(payload.get("locale"), "manifest.locale", "manifest_invalid"),
        display_name=_text(payload.get("display_name"), "manifest.display_name", "manifest_invalid"),
        pack_version=_text(payload.get("pack_version"), "manifest.pack_version", "manifest_invalid"),
        feature_contract_hash=_text(
            payload.get("feature_contract_hash"),
            "manifest.feature_contract_hash",
            "manifest_invalid",
        ),
    )
    return _ParsedManifest(manifest, references)


def _read_verified_resource(
    pack_root: Path,
    name: str,
    reference: _ResourceReference,
) -> dict[str, Any]:
    path = _resolve_contained(
        pack_root,
        reference.path,
        f"manifest.resources.{name}.path",
        "resource_path_invalid",
    )
    raw = _read_bytes(path, reason="pack_missing")
    if hashlib.sha256(raw).hexdigest() != reference.sha256:
        _fail(
            "checksum_mismatch",
            f"manifest.resources.{name}.sha256",
            "resource checksum does not match manifest",
        )
    return _decode_yaml(raw, str(path), "inventory_mismatch")


def _parse_resources(payloads: dict[str, dict[str, Any]]) -> ActionLanguageResources:
    app = payloads["app"]
    _schema(app, 1, "resources.app")
    _reject_unknown(
        app,
        {"schema_version", "default_system_prompt"},
        "resources.app",
        "inventory_mismatch",
    )
    actions = payloads["actions"]
    _schema(actions, 1, "resources.actions")
    _reject_unknown(
        actions,
        {"schema_version", "actions"},
        "resources.actions",
        "inventory_mismatch",
    )
    action_map = _mapping(actions.get("actions"), "resources.actions.actions", "inventory_mismatch")
    localized_actions = tuple(
        _parse_localized_action(action_id, value)
        for action_id, value in action_map.items()
    )

    profiles = payloads["output_profiles"]
    _schema(profiles, 1, "resources.output_profiles")
    _reject_unknown(
        profiles,
        {"schema_version", "profiles"},
        "resources.output_profiles",
        "inventory_mismatch",
    )
    profile_map = _mapping(
        profiles.get("profiles"),
        "resources.output_profiles.profiles",
        "inventory_mismatch",
    )
    localized_profiles = tuple(
        _parse_localized_profile(profile_id, value)
        for profile_id, value in profile_map.items()
    )
    entry_panel = payloads["entry_panel"]
    _schema(entry_panel, 1, "resources.entry_panel")
    _reject_unknown(
        entry_panel,
        {"schema_version", "candidates"},
        "resources.entry_panel",
        "inventory_mismatch",
    )
    localized_candidates = tuple(
        _parse_localized_entry_panel_candidate(
            value,
            f"resources.entry_panel.candidates[{index}]",
        )
        for index, value in enumerate(
            _list(
                entry_panel.get("candidates"),
                "resources.entry_panel.candidates",
                "inventory_mismatch",
            )
        )
    )
    return ActionLanguageResources(
        default_system_prompt=_text(
            app.get("default_system_prompt"),
            "resources.app.default_system_prompt",
            "inventory_mismatch",
            preserve=True,
        ),
        actions=localized_actions,
        output_profiles=localized_profiles,
        entry_panel_candidates=localized_candidates,
    )


def _parse_localized_action(action_id: str, value: Any) -> LocalizedAction:
    path = f"resources.actions.actions.{action_id}"
    data = _mapping(value, path, "inventory_mismatch")
    _reject_unknown(
        data,
        {"name", "system_prompt", "prompt", "feedback", "variants"},
        path,
        "inventory_mismatch",
    )
    variants = _mapping(data.get("variants", {}), f"{path}.variants", "inventory_mismatch")
    return LocalizedAction(
        id=action_id,
        name=_text(data.get("name"), f"{path}.name", "inventory_mismatch", preserve=True),
        system_prompt=_text(
            data.get("system_prompt"),
            f"{path}.system_prompt",
            "inventory_mismatch",
            preserve=True,
        ),
        prompt=_text(data.get("prompt"), f"{path}.prompt", "inventory_mismatch", preserve=True),
        feedback=_parse_localized_feedback(data.get("feedback"), f"{path}.feedback"),
        variants=tuple(
            _parse_localized_variant(press_type, variant, f"{path}.variants.{press_type}")
            for press_type, variant in variants.items()
        ),
    )


def _parse_localized_variant(
    press_type: str,
    value: Any,
    path: str,
) -> LocalizedActionVariant:
    if press_type not in {"short", "long"}:
        _fail("inventory_mismatch", path, "unsupported press variant")
    data = _mapping(value, path, "inventory_mismatch")
    _reject_unknown(
        data,
        {"name", "system_prompt", "prompt", "feedback"},
        path,
        "inventory_mismatch",
    )
    return LocalizedActionVariant(
        press_type=cast(PressType, press_type),
        name=_text(data.get("name"), f"{path}.name", "inventory_mismatch", preserve=True),
        system_prompt=_text(
            data.get("system_prompt"),
            f"{path}.system_prompt",
            "inventory_mismatch",
            preserve=True,
        ),
        prompt=_text(data.get("prompt"), f"{path}.prompt", "inventory_mismatch", preserve=True),
        feedback=_parse_localized_feedback(data.get("feedback"), f"{path}.feedback"),
    )


def _parse_localized_feedback(value: Any, path: str) -> LocalizedFeedback | None:
    if value is None:
        return None
    data = _mapping(value, path, "feedback_contract_mismatch")
    _reject_unknown(
        data,
        {"helps", "does_not", "reasons"},
        path,
        "feedback_contract_mismatch",
    )
    reasons = _mapping(data.get("reasons"), f"{path}.reasons", "feedback_contract_mismatch")
    return LocalizedFeedback(
        helps=_text(data.get("helps"), f"{path}.helps", "feedback_contract_mismatch", preserve=True),
        does_not=_text(
            data.get("does_not"),
            f"{path}.does_not",
            "feedback_contract_mismatch",
            preserve=True,
        ),
        reasons=tuple(
            FeedbackReason(
                reason_id,
                _text(label, f"{path}.reasons.{reason_id}", "feedback_contract_mismatch", preserve=True),
            )
            for reason_id, label in reasons.items()
        ),
    )


def _parse_localized_profile(profile_id: str, value: Any) -> LocalizedOutputProfile:
    path = f"resources.output_profiles.profiles.{profile_id}"
    data = _mapping(value, path, "marker_contract_mismatch")
    _reject_unknown(
        data,
        {"instruction", "markers"},
        path,
        "marker_contract_mismatch",
    )
    markers = _mapping(data.get("markers", {}), f"{path}.markers", "marker_contract_mismatch")
    return LocalizedOutputProfile(
        id=profile_id,
        instruction=_text(
            data.get("instruction"),
            f"{path}.instruction",
            "inventory_mismatch",
            allow_empty=profile_id == "plain_text",
            preserve=True,
        ),
        markers=tuple(
            LocalizedMarker(
                marker_id,
                _text(literal, f"{path}.markers.{marker_id}", "marker_contract_mismatch", preserve=True),
            )
            for marker_id, literal in markers.items()
        ),
    )


def _parse_localized_entry_panel_candidate(
    value: Any,
    path: str,
) -> LocalizedEntryPanelCandidate:
    data = _mapping(value, path, "inventory_mismatch")
    _reject_unknown(
        data,
        {"action_id", "press_type", "label", "description"},
        path,
        "inventory_mismatch",
    )
    press_type = _choice(
        data.get("press_type"),
        {"short", "long"},
        f"{path}.press_type",
        "inventory_mismatch",
    )
    return LocalizedEntryPanelCandidate(
        action_id=_text(
            data.get("action_id"),
            f"{path}.action_id",
            "inventory_mismatch",
        ),
        press_type=cast(PressType, press_type),
        label=_text(
            data.get("label"),
            f"{path}.label",
            "inventory_mismatch",
            preserve=True,
        ),
        description=_text(
            data.get("description"),
            f"{path}.description",
            "inventory_mismatch",
            preserve=True,
        ),
    )


def _parse_action_skeleton(path: Path) -> tuple[ActionSkeleton, ...]:
    payload = _read_yaml(path, reason="contract_mismatch")
    _schema(payload, ACTION_SKELETON_SCHEMA_VERSION, "skeleton.actions")
    _reject_unknown(payload, {"schema_version", "actions"}, "skeleton.actions", "contract_mismatch")
    raw_actions = _list(payload.get("actions"), "skeleton.actions.actions", "contract_mismatch")
    actions: list[ActionSkeleton] = []
    for index, value in enumerate(raw_actions):
        item_path = f"skeleton.actions.actions[{index}]"
        data = _mapping(value, item_path, "contract_mismatch")
        _reject_unknown(
            data,
            {
                "id", "stream", "input_mode", "output_mode", "temperature",
                "output_profile", "external_fallback", "personal_style_mode",
                "prompt_variables", "feedback_reason_ids", "press_variants",
            },
            item_path,
            "contract_mismatch",
        )
        action_id = _text(data.get("id"), f"{item_path}.id", "contract_mismatch")
        raw_variants = _mapping(data.get("press_variants", {}), f"{item_path}.press_variants", "contract_mismatch")
        variants = tuple(
            _parse_variant_skeleton(press_type, variant, f"{item_path}.press_variants.{press_type}")
            for press_type, variant in raw_variants.items()
        )
        input_mode = _choice(
            data.get("input_mode", "selection_or_clipboard"),
            {"clipboard", "clipboard_image", "selection_or_clipboard"},
            f"{item_path}.input_mode",
        )
        output_mode = _choice(data.get("output_mode", "popup"), {"popup"}, f"{item_path}.output_mode")
        fallback = _choice(
            data.get("external_fallback", "selection_or_clipboard"),
            {"selection_or_clipboard", "clipboard"},
            f"{item_path}.external_fallback",
        )
        style = data.get("personal_style_mode")
        if style is not None:
            style = _choice(style, {"formal", "informal"}, f"{item_path}.personal_style_mode")
        actions.append(ActionSkeleton(
            id=action_id,
            stream=_optional_boolean(data.get("stream"), f"{item_path}.stream"),
            input_mode=cast(InputMode, input_mode),
            output_mode=cast(OutputMode, output_mode),
            temperature=_optional_number(data.get("temperature"), f"{item_path}.temperature"),
            output_profile=_text(data.get("output_profile", "plain_text"), f"{item_path}.output_profile", "contract_mismatch"),
            external_fallback=cast(ExternalFallback, fallback),
            personal_style_mode=cast(PersonalStyleMode | None, style),
            prompt_variables=_string_tuple(data.get("prompt_variables"), f"{item_path}.prompt_variables"),
            feedback_reason_ids=_optional_string_tuple(data.get("feedback_reason_ids"), f"{item_path}.feedback_reason_ids"),
            variants=variants,
        ))
    return tuple(actions)


def _parse_variant_skeleton(press_type: str, value: Any, path: str) -> ActionVariantSkeleton:
    if press_type not in {"short", "long"}:
        _fail("contract_mismatch", path, "unsupported press variant")
    data = _mapping(value, path, "contract_mismatch")
    _reject_unknown(data, {"output_profile", "prompt_variables", "feedback_reason_ids"}, path, "contract_mismatch")
    return ActionVariantSkeleton(
        press_type=cast(PressType, press_type),
        output_profile=(
            _text(data["output_profile"], f"{path}.output_profile", "contract_mismatch")
            if "output_profile" in data else None
        ),
        prompt_variables=_string_tuple(data.get("prompt_variables"), f"{path}.prompt_variables"),
        feedback_reason_ids=_optional_string_tuple(data.get("feedback_reason_ids"), f"{path}.feedback_reason_ids"),
    )


def _parse_shortcut_skeleton(path: Path) -> tuple[ShortcutDefinition, ...]:
    payload = _read_yaml(path, reason="contract_mismatch")
    _schema(payload, 1, "skeleton.shortcuts")
    _reject_unknown(payload, {"schema_version", "shortcuts"}, "skeleton.shortcuts", "contract_mismatch")
    raw_shortcuts = _list(payload.get("shortcuts"), "skeleton.shortcuts.shortcuts", "contract_mismatch")
    shortcuts: list[ShortcutDefinition] = []
    for index, value in enumerate(raw_shortcuts):
        item_path = f"skeleton.shortcuts.shortcuts[{index}]"
        data = _mapping(value, item_path, "contract_mismatch")
        _reject_unknown(data, {"id", "hotkey", "command", "action_id"}, item_path, "contract_mismatch")
        command = _choice(
            data.get("command"),
            {"start_action", "open_contextual_question", "speak_selection_or_clipboard", "push_to_talk"},
            f"{item_path}.command",
        )
        action_id = data.get("action_id")
        if action_id is not None:
            action_id = _text(action_id, f"{item_path}.action_id", "contract_mismatch")
        shortcuts.append(ShortcutDefinition(
            id=_text(data.get("id"), f"{item_path}.id", "contract_mismatch"),
            hotkey=_text(data.get("hotkey"), f"{item_path}.hotkey", "contract_mismatch").lower(),
            command=cast(ShortcutCommandKind, command),
            action_id=cast(str | None, action_id),
        ))
    return tuple(shortcuts)


def _parse_output_profile_skeleton(path: Path) -> tuple[OutputProfileSkeleton, ...]:
    payload = _read_yaml(path, reason="contract_mismatch")
    _schema(payload, OUTPUT_PROFILE_SKELETON_SCHEMA_VERSION, "skeleton.output_profiles")
    _reject_unknown(payload, {"schema_version", "profiles"}, "skeleton.output_profiles", "contract_mismatch")
    raw_profiles = _list(payload.get("profiles"), "skeleton.output_profiles.profiles", "contract_mismatch")
    profiles: list[OutputProfileSkeleton] = []
    for index, value in enumerate(raw_profiles):
        item_path = f"skeleton.output_profiles.profiles[{index}]"
        data = _mapping(value, item_path, "contract_mismatch")
        _reject_unknown(data, {"id", "presentation", "markers"}, item_path, "contract_mismatch")
        markers = tuple(
            _parse_marker_skeleton(marker, f"{item_path}.markers[{marker_index}]")
            for marker_index, marker in enumerate(_list(data.get("markers", []), f"{item_path}.markers", "contract_mismatch"))
        )
        profiles.append(OutputProfileSkeleton(
            id=_text(data.get("id"), f"{item_path}.id", "contract_mismatch"),
            presentation=_text(data.get("presentation"), f"{item_path}.presentation", "contract_mismatch"),
            markers=markers,
        ))
    return tuple(profiles)


def _parse_entry_panel_skeleton(
    path: Path,
) -> tuple[EntryPanelCategorySkeleton, ...]:
    payload = _read_yaml(path, reason="contract_mismatch")
    _schema(
        payload,
        ENTRY_PANEL_SKELETON_SCHEMA_VERSION,
        "skeleton.entry_panel",
    )
    _reject_unknown(
        payload,
        {"schema_version", "categories"},
        "skeleton.entry_panel",
        "contract_mismatch",
    )
    raw_categories = _list(
        payload.get("categories"),
        "skeleton.entry_panel.categories",
        "contract_mismatch",
    )
    categories: list[EntryPanelCategorySkeleton] = []
    for index, value in enumerate(raw_categories):
        category_path = f"skeleton.entry_panel.categories[{index}]"
        data = _mapping(value, category_path, "contract_mismatch")
        _reject_unknown(
            data,
            {"id", "slot", "label", "description", "flagship", "advanced"},
            category_path,
            "contract_mismatch",
        )
        _text(data.get("label"), f"{category_path}.label", "contract_mismatch")
        _text(
            data.get("description"),
            f"{category_path}.description",
            "contract_mismatch",
        )
        categories.append(
            EntryPanelCategorySkeleton(
                category_id=_text(
                    data.get("id"),
                    f"{category_path}.id",
                    "contract_mismatch",
                ),
                slot=_integer(
                    data.get("slot"),
                    f"{category_path}.slot",
                    "contract_mismatch",
                ),
                flagship=_parse_entry_panel_candidate_skeletons(
                    data.get("flagship"),
                    f"{category_path}.flagship",
                ),
                advanced=_parse_entry_panel_candidate_skeletons(
                    data.get("advanced"),
                    f"{category_path}.advanced",
                ),
            )
        )
    return tuple(categories)


def _parse_entry_panel_candidate_skeletons(
    value: Any,
    path: str,
) -> tuple[EntryPanelCandidateSkeleton, ...]:
    candidates: list[EntryPanelCandidateSkeleton] = []
    for index, item in enumerate(_list(value, path, "contract_mismatch")):
        candidate_path = f"{path}[{index}]"
        data = _mapping(item, candidate_path, "contract_mismatch")
        _reject_unknown(
            data,
            {"action_id", "press_type"},
            candidate_path,
            "contract_mismatch",
        )
        press_type = _choice(
            data.get("press_type"),
            {"short", "long"},
            f"{candidate_path}.press_type",
        )
        candidates.append(
            EntryPanelCandidateSkeleton(
                action_id=_text(
                    data.get("action_id"),
                    f"{candidate_path}.action_id",
                    "contract_mismatch",
                ),
                press_type=cast(PressType, press_type),
            )
        )
    return tuple(candidates)


def _parse_marker_skeleton(value: Any, path: str) -> OutputMarkerSkeleton:
    data = _mapping(value, path, "marker_contract_mismatch")
    _reject_unknown(data, {"marker_id", "kind", "literal"}, path, "marker_contract_mismatch")
    kind = _choice(data.get("kind"), {"localized", "control_token"}, f"{path}.kind", "marker_contract_mismatch")
    return OutputMarkerSkeleton(
        marker_id=_text(data.get("marker_id"), f"{path}.marker_id", "marker_contract_mismatch"),
        kind=cast(Any, kind),
        literal=_text(data.get("literal", ""), f"{path}.literal", "marker_contract_mismatch", allow_empty=True, preserve=True),
    )


def _read_yaml(
    path: Path,
    *,
    reason: ActionLanguagePackErrorCode,
    missing_reason: ActionLanguagePackErrorCode | None = None,
) -> dict[str, Any]:
    return _decode_yaml(
        _read_bytes(path, reason=missing_reason or reason),
        str(path),
        reason,
    )


def _read_bytes(path: Path, *, reason: ActionLanguagePackErrorCode) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ActionLanguagePackError(reason, str(path), f"{path}: cannot read required file") from exc
    if len(raw) > MAX_LANGUAGE_PACK_FILE_BYTES:
        _fail(reason, str(path), "file exceeds the supported size limit")
    return raw


def _decode_yaml(raw: bytes, path: str, reason: ActionLanguagePackErrorCode) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActionLanguagePackError(reason, path, f"{path}: file is not valid UTF-8") from exc
    try:
        payload = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ActionLanguagePackError(reason, path, f"{path}: invalid YAML") from exc
    return _mapping(payload, path, reason)


def _resolve_contained(
    root: Path,
    relative: str,
    path: str,
    reason: ActionLanguagePackErrorCode,
) -> Path:
    candidate_value = Path(relative)
    if candidate_value.is_absolute() or ".." in candidate_value.parts:
        _fail(reason, path, "path must be relative and remain inside its owner directory")
    root_resolved = root.resolve()
    candidate = (root_resolved / candidate_value).resolve()
    if not candidate.is_relative_to(root_resolved):
        _fail(reason, path, "resolved path escapes its owner directory")
    return candidate


def _schema(data: dict[str, Any], expected: int, path: str) -> None:
    value = data.get("schema_version")
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        reason: ActionLanguagePackErrorCode = (
            "manifest_invalid" if path == "manifest" else
            "registry_invalid" if path == "registry" else
            "contract_mismatch" if path.startswith("skeleton") else
            "inventory_mismatch"
        )
        _fail(reason, f"{path}.schema_version", "unsupported or missing schema version")


def _reject_unknown(
    data: dict[str, Any],
    allowed: set[str],
    path: str,
    reason: ActionLanguagePackErrorCode,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(reason, f"{path}.{unknown[0]}", "unsupported field")


def _mapping(value: Any, path: str, reason: ActionLanguagePackErrorCode) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail(reason, path, "value must be a string-keyed mapping")
    return value


def _list(value: Any, path: str, reason: ActionLanguagePackErrorCode) -> list[Any]:
    if not isinstance(value, list):
        _fail(reason, path, "value must be a list")
    return value


def _text(
    value: Any,
    path: str,
    reason: ActionLanguagePackErrorCode,
    *,
    allow_empty: bool = False,
    preserve: bool = False,
) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail(reason, path, "value must be a non-empty string")
    return value if preserve else value.strip()


def _integer(value: Any, path: str, reason: ActionLanguagePackErrorCode) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(reason, path, "value must be an integer")
    return value


def _choice(
    value: Any,
    allowed: set[str],
    path: str,
    reason: ActionLanguagePackErrorCode = "contract_mismatch",
) -> str:
    result = _text(value, path, reason)
    if result not in allowed:
        _fail(reason, path, "value is not supported")
    return result


def _optional_boolean(value: Any, path: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        _fail("contract_mismatch", path, "value must be true or false")
    return value


def _optional_number(value: Any, path: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("contract_mismatch", path, "value must be a number")
    return float(value)


def _string_tuple(value: Any, path: str) -> tuple[str, ...]:
    return _required_string_tuple(value, path, optional=False) or ()


def _optional_string_tuple(value: Any, path: str) -> tuple[str, ...] | None:
    return _required_string_tuple(value, path, optional=True)


def _required_string_tuple(
    value: Any,
    path: str,
    *,
    optional: bool,
) -> tuple[str, ...] | None:
    if value is None and optional:
        return None
    items = _list(value, path, "contract_mismatch")
    if not items or not all(isinstance(item, str) and item.strip() for item in items):
        _fail("contract_mismatch", path, "value must contain non-empty string ids")
    return tuple(item.strip() for item in items)


def _fail(
    reason: ActionLanguagePackErrorCode,
    path: str,
    message: str,
) -> NoReturn:
    raise ActionLanguagePackError(reason, path, f"{path}: {message}")
