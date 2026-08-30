from __future__ import annotations

from ClipAI.app.language_pack_loader import (
    ActionLanguagePackLoader,
    LanguagePackRegistryEntry,
    load_feature_skeleton,
    validate_official_language_packs,
)
from ClipAI.core.models import ActionDefinition


def _load(pack_id: str):
    loader = ActionLanguagePackLoader("config", load_feature_skeleton("config"))
    return loader.load(
        LanguagePackRegistryEntry(pack_id, f"language_packs/{pack_id}")
    )


def _action(pack, action_id: str) -> ActionDefinition:
    return next(
        action for action in pack.action_definitions if action.id == action_id
    )


def _feedback_reason_ids(action: ActionDefinition) -> tuple[str, ...] | None:
    if action.feedback_contract is None:
        return None
    return tuple(reason.id for reason in action.feedback_contract.reasons)


def _behavior(action: ActionDefinition) -> tuple[object, ...]:
    return (
        action.stream,
        action.input_mode,
        action.output_mode,
        action.temperature,
        action.output_profile,
        action.external_fallback,
        action.personal_style_mode,
        tuple(
            (press_type, variant.output_profile)
            for press_type, variant in action.press_variants.items()
        ),
    )


def test_japanese_candidate_compiles_as_one_complete_pack() -> None:
    pack = _load("ja-JP")

    assert pack.descriptor.identity.pack_id == "ja-JP"
    assert pack.descriptor.identity.locale == "ja-JP"
    assert pack.descriptor.display_name == "日本語"
    assert len(pack.action_definitions) == 27
    assert len(pack.output_profiles) == 10


def test_official_registry_releases_both_complete_packs_in_product_order() -> None:
    packs = validate_official_language_packs("config")

    assert tuple(pack.descriptor.identity.pack_id for pack in packs) == (
        "zh-TW",
        "ja-JP",
    )
    assert tuple(pack.descriptor.display_name for pack in packs) == (
        "繁體中文",
        "日本語",
    )


def test_japanese_pack_preserves_fixed_output_language_semantics() -> None:
    pack = _load("ja-JP")
    traditional_chinese = _action(pack, "translate_to_traditional_chinese")
    english = _action(pack, "translate_to_english")
    japanese = english.press_variants["long"]
    shorten = _action(pack, "shorten_content")

    assert "繁体字中国語" in traditional_chinese.system_prompt
    assert "繁体字中国語" in traditional_chinese.prompt
    assert "英語" in english.system_prompt
    assert "英語" in english.prompt
    assert "日本語" in japanese.system_prompt
    assert "日本語" in japanese.prompt
    assert "英語は英語" in shorten.system_prompt
    assert "元の言語を保ち" in shorten.prompt
    assert "翻訳や新しい構造を追加しません" in shorten.prompt


def test_official_pack_candidates_share_exact_behavior_topology() -> None:
    traditional_chinese = _load("zh-TW")
    japanese = _load("ja-JP")

    assert tuple(action.id for action in japanese.action_definitions) == tuple(
        action.id for action in traditional_chinese.action_definitions
    )
    assert tuple(profile.id for profile in japanese.output_profiles) == tuple(
        profile.id for profile in traditional_chinese.output_profiles
    )
    for zh_action, ja_action in zip(
        traditional_chinese.action_definitions,
        japanese.action_definitions,
        strict=True,
    ):
        assert _behavior(ja_action) == _behavior(zh_action)
        assert tuple(ja_action.press_variants) == tuple(zh_action.press_variants)
        assert _feedback_reason_ids(ja_action) == _feedback_reason_ids(zh_action)
        for press_type in ja_action.press_variants:
            assert _feedback_reason_ids(
                ja_action.press_variants[press_type]
            ) == _feedback_reason_ids(zh_action.press_variants[press_type])
    for zh_profile, ja_profile in zip(
        traditional_chinese.output_profiles,
        japanese.output_profiles,
        strict=True,
    ):
        assert ja_profile.presentation == zh_profile.presentation


def test_language_pack_content_changes_action_version_identity() -> None:
    traditional_chinese = _load("zh-TW")
    japanese = _load("ja-JP")

    assert (
        traditional_chinese.provenance.resource_content_hash
        != japanese.provenance.resource_content_hash
    )
    assert traditional_chinese.version_context != japanese.version_context
