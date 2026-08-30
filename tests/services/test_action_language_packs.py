from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from ClipAI.core.errors import ActionLanguagePackError
from ClipAI.core.models import FeedbackReason, ShortcutDefinition
from ClipAI.services.action_language_packs import (
    ActionLanguagePackManifest,
    ActionLanguageResources,
    ActionSkeleton,
    ActionVariantSkeleton,
    FeatureSkeleton,
    LocalizedAction,
    LocalizedActionVariant,
    LocalizedFeedback,
    LocalizedMarker,
    LocalizedOutputProfile,
    OutputMarkerSkeleton,
    OutputProfileSkeleton,
    compile_pack,
    feature_contract_hash,
)


def _valid_contract() -> tuple[
    FeatureSkeleton,
    ActionLanguagePackManifest,
    ActionLanguageResources,
]:
    skeleton = FeatureSkeleton(
        actions=(
            ActionSkeleton(
                id="explain",
                stream=True,
                temperature=0.2,
                output_profile="structured",
                feedback_reason_ids=("incorrect", "other"),
                variants=(ActionVariantSkeleton(press_type="long"),),
            ),
        ),
        shortcuts=(
            ShortcutDefinition(
                id="explain",
                hotkey="ctrl+alt+e",
                command="start_action",
                action_id="explain",
            ),
            ShortcutDefinition(
                id="speak",
                hotkey="ctrl+alt+q",
                command="speak_selection_or_clipboard",
            ),
        ),
        output_profiles=(
            OutputProfileSkeleton(id="plain_text", presentation="plain_text"),
            OutputProfileSkeleton(
                id="structured",
                presentation="markdown_sections",
                markers=(
                    OutputMarkerSkeleton("heading", "localized"),
                    OutputMarkerSkeleton(
                        "scroll_break",
                        "control_token",
                        "[[SCROLL_BREAK]]",
                    ),
                ),
            ),
        ),
    )
    manifest = ActionLanguagePackManifest(
        schema_version=1,
        pack_id="zh-TW",
        locale="zh-TW",
        display_name="繁體中文",
        pack_version="1.0.0",
        feature_contract_hash=feature_contract_hash(skeleton),
    )
    feedback = LocalizedFeedback(
        helps="幫你解釋",
        does_not="不替你判斷",
        reasons=(
            FeedbackReason("incorrect", "內容不正確"),
            FeedbackReason("other", "其他"),
        ),
    )
    resources = ActionLanguageResources(
        default_system_prompt="你是一位有幫助的助理。",
        actions=(
            LocalizedAction(
                id="explain",
                name="解釋",
                system_prompt="忠實解釋輸入。",
                prompt="請解釋：{input}",
                feedback=feedback,
                variants=(
                    LocalizedActionVariant(
                        press_type="long",
                        name="詳細解釋",
                        system_prompt="忠實且詳細地解釋輸入。",
                        prompt="請詳細解釋：{input}",
                    ),
                ),
            ),
        ),
        output_profiles=(
            LocalizedOutputProfile(id="plain_text", instruction=""),
            LocalizedOutputProfile(
                id="structured",
                instruction="使用指定段落。",
                markers=(LocalizedMarker("heading", "## 解釋"),),
            ),
        ),
    )
    return skeleton, manifest, resources


def _replace_action(
    resources: ActionLanguageResources,
    **changes: Any,
) -> ActionLanguageResources:
    return replace(
        resources,
        actions=(replace(resources.actions[0], **changes),),
    )


def _assert_failure(
    skeleton: FeatureSkeleton,
    manifest: ActionLanguagePackManifest,
    resources: ActionLanguageResources,
    reason: str,
) -> ActionLanguagePackError:
    with pytest.raises(ActionLanguagePackError) as caught:
        compile_pack(skeleton, manifest, resources)
    assert caught.value.reason == reason
    assert caught.value.path
    return caught.value


def test_valid_pack_compiles_complete_existing_domain_models() -> None:
    skeleton, manifest, resources = _valid_contract()

    compiled = compile_pack(skeleton, manifest, resources)

    assert compiled.descriptor.identity.pack_id == "zh-TW"
    assert compiled.descriptor.display_name == "繁體中文"
    assert compiled.provenance.feature_contract_hash == manifest.feature_contract_hash
    assert compiled.provenance.resource_content_hash.startswith("sha256:")
    assert compiled.default_system_prompt == resources.default_system_prompt
    assert len(compiled.action_definitions) == 1
    action = compiled.action_definitions[0]
    assert action.output_profile == "structured"
    assert action.feedback_contract is not None
    assert action.feedback_contract.ai_help_label == "幫你解釋"
    assert tuple(reason.id for reason in action.feedback_contract.reasons) == (
        "incorrect",
        "other",
    )
    assert action.press_variants["long"].feedback_contract is None
    assert compiled.output_profiles[1].required_markers == (
        "## 解釋",
        "[[SCROLL_BREAK]]",
    )


@pytest.mark.parametrize(
    "manifest_change",
    (
        {"schema_version": 0},
        {"schema_version": 2},
        {"pack_id": "bad/id"},
        {"locale": ""},
        {"display_name": ""},
        {"pack_version": "1.0"},
        {"pack_version": "01.0.0"},
    ),
)
def test_manifest_contract_rejects_unsupported_or_invalid_values(
    manifest_change: dict[str, Any],
) -> None:
    skeleton, manifest, resources = _valid_contract()

    _assert_failure(
        skeleton,
        replace(manifest, **manifest_change),
        resources,
        "manifest_invalid",
    )


def test_contract_hash_mismatch_is_typed_and_does_not_compile_partial_result() -> None:
    skeleton, manifest, resources = _valid_contract()

    error = _assert_failure(
        skeleton,
        replace(manifest, feature_contract_hash="sha256:stale"),
        resources,
        "contract_mismatch",
    )

    assert error.path == "manifest.feature_contract_hash"


@pytest.mark.parametrize("kind", ("missing", "extra", "duplicate"))
def test_action_inventory_must_match_exactly(kind: str) -> None:
    skeleton, manifest, resources = _valid_contract()
    action = resources.actions[0]
    actions: tuple[LocalizedAction, ...]
    if kind == "missing":
        actions = ()
    elif kind == "extra":
        actions = (*resources.actions, replace(action, id="extra"))
    else:
        actions = (*resources.actions, action)

    _assert_failure(
        skeleton,
        manifest,
        replace(resources, actions=actions),
        "inventory_mismatch",
    )


@pytest.mark.parametrize("kind", ("missing", "extra", "duplicate"))
def test_explicit_variant_topology_must_match_exactly(kind: str) -> None:
    skeleton, manifest, resources = _valid_contract()
    variant = resources.actions[0].variants[0]
    variants: tuple[LocalizedActionVariant, ...]
    if kind == "missing":
        variants = ()
    elif kind == "extra":
        variants = (*resources.actions[0].variants, replace(variant, press_type="short"))
    else:
        variants = (*resources.actions[0].variants, variant)

    _assert_failure(
        skeleton,
        manifest,
        _replace_action(resources, variants=variants),
        "inventory_mismatch",
    )


@pytest.mark.parametrize(
    "feedback",
    (
        None,
        LocalizedFeedback(
            "幫你解釋",
            "不替你判斷",
            (FeedbackReason("other", "其他"), FeedbackReason("incorrect", "錯誤")),
        ),
        LocalizedFeedback(
            "幫你解釋",
            "不替你判斷",
            (FeedbackReason("incorrect", "錯誤"),),
        ),
    ),
)
def test_feedback_reason_inventory_and_order_are_exact(
    feedback: LocalizedFeedback | None,
) -> None:
    skeleton, manifest, resources = _valid_contract()

    _assert_failure(
        skeleton,
        manifest,
        _replace_action(resources, feedback=feedback),
        "feedback_contract_mismatch",
    )


def test_variant_feedback_inheritance_topology_is_owned_by_skeleton() -> None:
    skeleton, manifest, resources = _valid_contract()
    inherited_feedback = resources.actions[0].feedback
    variant = replace(resources.actions[0].variants[0], feedback=inherited_feedback)

    _assert_failure(
        skeleton,
        manifest,
        _replace_action(resources, variants=(variant,)),
        "feedback_contract_mismatch",
    )


def test_explicit_variant_feedback_override_compiles_when_declared() -> None:
    skeleton, _, resources = _valid_contract()
    variant_skeleton = replace(
        skeleton.actions[0].variants[0],
        feedback_reason_ids=("too_long", "other"),
    )
    skeleton = replace(
        skeleton,
        actions=(replace(skeleton.actions[0], variants=(variant_skeleton,)),),
    )
    variant_feedback = LocalizedFeedback(
        "幫你詳細解釋",
        "不替你做結論",
        (
            FeedbackReason("too_long", "太長"),
            FeedbackReason("other", "其他"),
        ),
    )
    resources = _replace_action(
        resources,
        variants=(replace(resources.actions[0].variants[0], feedback=variant_feedback),),
    )
    manifest = ActionLanguagePackManifest(
        schema_version=1,
        pack_id="ja-JP",
        locale="ja-JP",
        display_name="日本語",
        pack_version="1.2.3",
        feature_contract_hash=feature_contract_hash(skeleton),
    )

    compiled = compile_pack(skeleton, manifest, resources)

    compiled_feedback = (
        compiled.action_definitions[0]
        .press_variants["long"]
        .feedback_contract
    )
    assert compiled_feedback is not None
    assert compiled_feedback.reasons[0].id == "too_long"


@pytest.mark.parametrize("kind", ("missing", "extra", "duplicate"))
def test_output_profile_inventory_must_match_exactly(kind: str) -> None:
    skeleton, manifest, resources = _valid_contract()
    profile = resources.output_profiles[0]
    if kind == "missing":
        profiles = resources.output_profiles[1:]
    elif kind == "extra":
        profiles = (*resources.output_profiles, replace(profile, id="extra"))
    else:
        profiles = (*resources.output_profiles, profile)

    _assert_failure(
        skeleton,
        manifest,
        replace(resources, output_profiles=profiles),
        "inventory_mismatch",
    )


@pytest.mark.parametrize(
    "markers",
    (
        (),
        (LocalizedMarker("extra", "額外"),),
        (LocalizedMarker("scroll_break", "可翻譯控制字"),),
    ),
)
def test_localized_marker_inventory_rejects_missing_extra_and_control_tokens(
    markers: tuple[LocalizedMarker, ...],
) -> None:
    skeleton, manifest, resources = _valid_contract()
    structured = replace(resources.output_profiles[1], markers=markers)

    _assert_failure(
        skeleton,
        manifest,
        replace(resources, output_profiles=(resources.output_profiles[0], structured)),
        "marker_contract_mismatch",
    )


@pytest.mark.parametrize(
    "prompt",
    (
        "沒有變數",
        "{input} 又一次 {input}",
        "{inputs}",
        "{",
        "{input.foo}",
        "{input[0]}",
        "{input!r}",
        "{input:>10}",
        "{}",
    ),
)
def test_prompt_template_contract_fails_closed(prompt: str) -> None:
    skeleton, manifest, resources = _valid_contract()

    _assert_failure(
        skeleton,
        manifest,
        _replace_action(resources, prompt=prompt),
        "prompt_template_invalid",
    )


def test_non_template_prompt_resources_reject_placeholder_braces() -> None:
    skeleton, manifest, resources = _valid_contract()

    _assert_failure(
        skeleton,
        manifest,
        replace(resources, default_system_prompt="不要解析 {input}"),
        "prompt_template_invalid",
    )


def test_skeleton_rejects_unknown_profile_reference() -> None:
    skeleton, manifest, resources = _valid_contract()
    skeleton = replace(
        skeleton,
        actions=(replace(skeleton.actions[0], output_profile="missing"),),
    )

    _assert_failure(skeleton, manifest, resources, "contract_mismatch")


def test_contract_hash_is_deterministic_and_sequence_sensitive() -> None:
    skeleton, _, _ = _valid_contract()

    assert feature_contract_hash(skeleton) == feature_contract_hash(skeleton)
    assert feature_contract_hash(skeleton) != feature_contract_hash(
        replace(skeleton, shortcuts=tuple(reversed(skeleton.shortcuts)))
    )


def test_resource_mapping_order_does_not_change_provenance_hash() -> None:
    skeleton, manifest, resources = _valid_contract()
    compiled = compile_pack(skeleton, manifest, resources)
    reordered = replace(
        resources,
        output_profiles=tuple(reversed(resources.output_profiles)),
    )

    assert (
        compile_pack(skeleton, manifest, reordered).provenance.resource_content_hash
        == compiled.provenance.resource_content_hash
    )
