from __future__ import annotations

from pathlib import Path

import pytest

from ClipAI.app.config_loader import load_action_catalog, load_app_config, load_config_bundle, load_output_profiles, load_shortcut_catalog
from ClipAI.app.readiness import assess_provider_readiness
from ClipAI.core.errors import ConfigError
from ClipAI.core.commands import SpeakSelectionOrClipboard, StartAction
from ClipAI.providers.settings import ProviderCredential


def test_config_bundle_loads_typed_provider_and_action_settings() -> None:
    bundle = load_config_bundle()

    assert bundle.providers.active == "gemini"
    assert bundle.runtime.maintenance_workers == 1
    assert bundle.app.modifier_mode == "ctrl_alt"
    assert bundle.tts.japanese_voice == "ja-JP-NanamiNeural"
    assert "1–2 秒看懂" in bundle.app.system_prompt
    assert "預設不超過 5 行或 120 字" in bundle.app.system_prompt
    assert "不主動加例子" in bundle.app.system_prompt
    action = bundle.actions.get("english_companion")
    assert action.input_mode == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is None
    assert action.temperature == 0.2
    assert action.output_profile == "english_learning_compact"
    assert bundle.output_profiles.get(action.output_profile).required_markers == ()
    assert bundle.output_profiles.get(action.output_profile).presentation == "plain_text"
    assert "When the input contains English" in action.system_prompt
    assert "When the input is Chinese-only" in action.system_prompt
    assert "do not refuse merely because no English is present" in action.system_prompt
    assert "concrete real-life situation" in action.system_prompt
    assert "Avoid formulaic wording" in action.prompt
    assert "Put only the expression on the first line" in action.prompt
    assert "Do not attach any spoken/written or formal/informal label" in action.prompt
    assert "After the example, add a separate `語感：` line" in action.prompt
    assert "mark each conversational option with `（口語常用）`" in action.prompt
    assert "記憶：" in action.prompt
    profile = bundle.output_profiles.get(action.output_profile)
    assert "without any spoken/written or formal/informal label" in profile.instruction
    assert "After the example, add a separate `語感：` line" in profile.instruction
    assert "mark conversational alternatives with `（口語常用）`" in profile.instruction
    assert bundle.schema_versions.app == 2
    assert bundle.schema_versions.actions == 9
    assert bundle.schema_versions.output_profiles == 1
    assert bundle.schema_versions.shortcuts == 1
    assert bundle.shortcuts.resolve("english_companion", "long").action_id == "english_companion"


def test_v4_context_actions_have_expected_hotkeys_and_support_multimodal_input() -> None:
    bundle = load_config_bundle()
    expected = {
        "translate_to_traditional_chinese": "ctrl+alt+1",
        "translate_to_english": "ctrl+alt+2",
        "name_idea": "ctrl+alt+3",
        "name_concept_carefully": "ctrl+alt+n",
        "illuminate_essence": "ctrl+alt+4",
        "pyramid_position": "ctrl+alt+5",
        "explain_like_friend": "ctrl+alt+6",
        "article_structure": "ctrl+alt+7",
        "english_companion": "ctrl+alt+8",
        "reflective_question": "ctrl+alt+9",
        "critical_thinking": "ctrl+alt+0",
        "mece_decomposition": "ctrl+alt+s",
            "minimum_action": "ctrl+alt+a",
            "tradeoff_perspective": "ctrl+alt+d",
            "temporary_viewpoint": "ctrl+alt+t",
            "extract_keywords": "ctrl+alt+e",
    }

    for shortcut_id, hotkey in expected.items():
        shortcut = bundle.shortcuts.definition(shortcut_id)
        assert shortcut.hotkey == hotkey
        assert shortcut.action_id == shortcut_id
        action = bundle.actions.get(shortcut.action_id)
        assert action.input_mode == "selection_or_clipboard"
        assert action.external_fallback == "selection_or_clipboard"
        assert "image" in action.system_prompt.lower() or "圖片" in action.system_prompt


def test_name_idea_keeps_two_part_format_without_markdown_headings() -> None:
    action = load_action_catalog("config/actions.yaml").get("name_idea")

    assert "第一段只放命名" in action.prompt
    assert "空一行後，第二段" in action.prompt
    assert "不要使用 Markdown heading" in action.prompt
    assert "## 洞察命名" not in action.prompt
    assert "## 想法原貌" not in action.prompt


def test_long_press_uses_variant_prompt() -> None:
    catalog = load_action_catalog("config/actions.yaml")
    resolved = catalog.resolve("english_companion", "long")
    assert resolved.name == "英文改善建議"
    assert "Improve the following English" in resolved.prompt
    assert resolved.output_profile == "english_improvement"
    assert resolved.prompt.index("Start with one polished full rewrite") < resolved.prompt.index("Then focus on")
    assert "do not invent a complete sentence or unsupported context" in resolved.prompt
    assert "only the 3-5 improvements" in resolved.prompt
    assert "exactly three separate lines" in resolved.prompt
    assert "Do not repeat the same correction" in resolved.prompt
    assert resolved.feedback_contract is not None
    assert resolved.feedback_contract.ai_help_label == "找出最影響英文自然度與清晰度的問題，提供改寫與可重用句型"

    profile = load_config_bundle().output_profiles.get(resolved.output_profile)
    assert profile.required_markers == (
        "## Full Rewrite",
        "## Key Improvements",
        "## Useful Patterns",
    )
    assert resolved.feedback_contract != catalog.resolve("english_companion", "short").feedback_contract


def test_ctrl_alt_u_resolves_capture_and_express_as_distinct_learning_intents() -> None:
    bundle = load_config_bundle()

    shortcut = bundle.shortcuts.definition("expression_retrieval")
    capture = bundle.actions.resolve(shortcut.action_id, "short")
    express = bundle.actions.resolve(shortcut.action_id, "long")

    assert shortcut.hotkey == "ctrl+alt+u"
    assert shortcut.action_id == "expression_retrieval"
    assert capture.name == "Capture an Expression"
    assert capture.stream is False
    assert capture.output_profile == "expression_capture"
    assert "without a Notice heading" in capture.prompt
    assert "without a Primary expression label" in capture.prompt
    assert "Without a Pattern heading" in capture.prompt
    assert "exactly three unnumbered bullet examples" in capture.prompt
    assert "Every bullet example must be a complete natural English sentence" in capture.prompt
    assert "Every example line must begin with the literal Markdown bullet `- `" in capture.prompt
    assert "smallest high-frequency spoken chunk" in capture.prompt
    assert "usually contain 2-8 English words" in capture.prompt
    assert "Use at most two semantic slots" in capture.prompt
    assert "Do not use grammar-class slots such as `[subject]`, `[noun phrase]`, or `[verb-ed]`" in capture.prompt
    assert "Bold only the fixed reusable words" in capture.prompt
    assert "Keep all replacement content unbolded" in capture.prompt
    assert "meaningfully different content" in capture.prompt
    assert "[[SCROLL_FOR_ANSWER]]" in capture.prompt
    assert "answer must appear only after" in capture.prompt
    assert express.name == "Express Naturally"
    assert express.stream is False
    assert express.output_profile == "expression_transfer"
    assert "without a Natural Version heading" in express.prompt
    assert "smallest original-to-improved comparison" in express.prompt
    assert "exactly one primary transfer chunk" in express.prompt
    assert "按 Ctrl+/ 回答" in express.prompt
    assert "evaluate only that transfer attempt" in express.system_prompt
    assert capture.feedback_contract is not None
    assert express.feedback_contract is not None
    assert capture.feedback_contract != express.feedback_contract

    capture_profile = bundle.output_profiles.get(capture.output_profile)
    express_profile = bundle.output_profiles.get(express.output_profile)
    assert capture_profile.required_markers == (
        "## Retrieve",
        "[[SCROLL_FOR_ANSWER]]",
        "## Make It Yours",
    )
    assert "Start with one valuable source sentence before any Markdown heading" in capture_profile.instruction
    assert "without a Primary expression label" in capture_profile.instruction
    assert "Never format English learning content as inline code or with backticks" in capture_profile.instruction
    assert "Do not prefix content with redundant field labels" in capture_profile.instruction
    assert "without a Pattern heading" in capture_profile.instruction
    assert "exactly three short unnumbered bullet examples" in capture_profile.instruction
    assert "Every bullet example and the Retrieve answer must be a complete English sentence" in capture_profile.instruction
    assert "Never use nested or unbalanced Markdown bold markers" in capture_profile.instruction
    assert "Every example line begins with the literal Markdown bullet `- `" in capture_profile.instruction
    assert "usually 2-8 English words" in capture_profile.instruction
    assert "at most two plain-language semantic slots" in capture_profile.instruction
    assert "Bold only the fixed reusable chunk" in capture_profile.instruction
    assert "Never bold slot labels or replacement content" in capture_profile.instruction
    assert "at most two bold spans per line" in capture_profile.instruction
    assert express_profile.required_markers == (
        "## Key Shift",
        "## Transfer Chunk",
        "## Your Turn",
    )
    assert "without a Natural Version heading" in express_profile.instruction
    assert "exactly one bold primary reusable chunk" in express_profile.instruction
    assert "按 Ctrl+/ 回答" in express_profile.instruction


def test_long_press_ctrl_alt_2_translates_to_japanese() -> None:
    bundle = load_config_bundle()

    shortcut = bundle.shortcuts.definition("translate_to_english")
    short_action = bundle.actions.resolve(shortcut.action_id, "short")
    long_action = bundle.actions.resolve(shortcut.action_id, "long")

    assert shortcut.hotkey == "ctrl+alt+2"
    assert short_action.name == "Translate to English"
    assert "natural English" in short_action.prompt
    assert long_action.name == "翻譯成日文"
    assert "natural Japanese" in long_action.prompt
    assert "Output only the Japanese translation" in long_action.system_prompt
    assert long_action.feedback_contract is not None
    assert long_action.feedback_contract.ai_help_label == "將內容翻譯成符合情境與關係的自然日文"
    assert long_action.feedback_contract != short_action.feedback_contract


def test_action_input_mode_defaults_to_selection_or_clipboard(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text(
        """schema_version: 3
actions:
  - id: default_input
    name: Default Input
    system_prompt: system
    prompt: "{input}"
  - id: clipboard_only
    name: Clipboard Only
    system_prompt: system
    prompt: "{input}"
    input_mode: clipboard
""",
        encoding="utf-8",
    )

    catalog = load_action_catalog(path)
    assert catalog.resolve("default_input", "short").input_mode == "selection_or_clipboard"
    assert catalog.resolve("clipboard_only", "short").input_mode == "clipboard"


def test_action_stream_inherits_catalog_default_and_allows_override(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text(
        """schema_version: 8
actions:
  - id: inherited
    name: Inherited
    system_prompt: system
    prompt: "{input}"
  - id: disabled
    name: Disabled
    system_prompt: system
    prompt: "{input}"
    stream: false
""",
        encoding="utf-8",
    )

    catalog = load_action_catalog(path, default_stream=True)

    assert catalog.get("inherited").stream is None
    assert catalog.resolve("inherited", "short").stream is True
    assert catalog.resolve("disabled", "short").stream is False


def test_unknown_config_field_reports_full_path(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
app:
  temperature: 0.2
  typo_field: true
provider:
  active: fake
  gemini: {}
  openai: {}
  anthropic: {}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"config\.app\.typo_field"):
        load_app_config(path)


def test_invalid_runtime_worker_count_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
app: {}
provider:
  active: fake
  gemini: {}
  openai: {}
  anthropic: {}
runtime:
  max_workers: 0
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="max_workers"):
        load_app_config(path)


def test_legacy_runtime_max_workers_migrates_to_maintenance_capacity(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "schema_version: 1\napp: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\nruntime:\n  max_workers: 3\n",
        encoding="utf-8",
    )
    _app, runtime, _providers, _tts, _voice, _logging = load_app_config(path)
    assert runtime.maintenance_workers == 3


def test_runtime_maintenance_capacity_defaults_to_one(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "schema_version: 2\napp: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\n",
        encoding="utf-8",
    )
    _app, runtime, _providers, _tts, _voice, _logging = load_app_config(path)
    assert runtime.maintenance_workers == 1


def test_runtime_rejects_new_and_legacy_worker_fields_together(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "schema_version: 2\napp: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\nruntime:\n  maintenance_workers: 1\n  max_workers: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="must not define both"):
        load_app_config(path)


@pytest.mark.parametrize(
    ("catalog", "message"),
    [
        ("[]", "at least one"),
        ("[gpt-4.1-mini, gpt-4.1-mini]", "duplicate model"),
        ("[gpt-4.1]", "include configured model"),
        ("[gpt-4.1-mini, '']", "non-empty string"),
    ],
)
def test_provider_model_catalog_is_validated(tmp_path: Path, catalog: str, message: str) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
app: {{}}
provider:
  active: openai
  gemini: {{}}
  openai:
    model: gpt-4.1-mini
    available_models: {catalog}
  anthropic: {{}}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=message):
        load_app_config(path)


def test_invalid_logging_level_is_rejected_by_config_loader(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "app: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\nlogging:\n  level: verbose\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"config\.logging\.level"):
        load_app_config(path)


def test_missing_schema_version_is_accepted_as_legacy_without_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    original = "app: {}\nprovider:\n  active: fake\n  gemini: {}\n  openai: {}\n  anthropic: {}\n"
    path.write_text(original, encoding="utf-8")
    load_app_config(path)
    assert path.read_text(encoding="utf-8") == original


def test_future_schema_version_reports_file_and_version(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("schema_version: 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"config\.yaml.*schema_version 3"):
        load_app_config(path)


@pytest.mark.parametrize(
    ("filename", "loader"),
    (("output_profiles.yaml", load_output_profiles),),
)
def test_future_catalog_schema_version_is_rejected(tmp_path: Path, filename: str, loader) -> None:
    path = tmp_path / filename
    path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"{filename}.*schema_version 2"):
        loader(path)


def test_future_actions_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text("schema_version: 10\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"actions.yaml.*schema_version 10"):
        load_action_catalog(path)


def test_feedback_contract_is_typed_for_enabled_actions() -> None:
    catalog = load_action_catalog("config/actions.yaml")

    translated = catalog.resolve("translate_to_english", "short")
    shortened = catalog.resolve("shorten_content", "short")
    dictation = catalog.resolve("intent_preserving_dictation_editor", "short")

    assert translated.feedback_contract is not None
    assert translated.feedback_contract.ai_help_label == "將內容翻譯成符合情境的自然英文"
    assert translated.feedback_contract.ai_does_not_label == "不替你決定真正想表達的意思、立場、關係拿捏與最後選擇"
    assert [(reason.id, reason.label) for reason in translated.feedback_contract.reasons] == [
        ("meaning_inaccurate", "語意不準確"),
        ("tone_or_formality_off", "語氣或正式程度不對"),
        ("terms_names_or_numbers_wrong", "術語、姓名或數字翻錯"),
        ("unnatural_or_wrong_audience", "說法不自然或不適合對象"),
        ("other", "其他"),
    ]
    assert shortened.feedback_contract is not None
    assert shortened.feedback_contract.ai_help_label == "縮短內容、移除重複，並維持原有結構"
    assert shortened.feedback_contract.ai_does_not_label == "不替你改變原本的立場、事實、語氣或語言"
    assert [(reason.id, reason.label) for reason in shortened.feedback_contract.reasons] == [
        ("meaning_or_fact_lost", "核心意思或重要事實少了"),
        ("key_detail_missing", "縮得太多，關鍵細節不夠"),
        ("voice_or_language_changed", "語氣、立場或原本語言被改掉"),
        ("length_or_structure_unusable", "長度或結構不適合直接使用"),
        ("other", "其他"),
    ]
    assert shortened.version_id
    assert dictation.feedback_contract is not None
    assert dictation.feedback_contract.ai_help_label == "將語音轉錄整理成自然、可直接閱讀或傳送的文字"
    assert dictation.feedback_contract.ai_does_not_label == "不替你改變最終意圖、獨特資訊、立場、不確定性或個人語氣"
    assert [(reason.id, reason.label) for reason in dictation.feedback_contract.reasons] == [
        ("meaning_or_detail_lost", "重要意思、細節或資訊被遺漏"),
        ("correction_or_repetition_wrong", "改口、自我修正或重複內容處理錯誤"),
        ("voice_stance_or_uncertainty_changed", "語氣、立場、猶豫或不確定性被改變"),
        ("punctuation_or_structure_unusable", "標點、段落、清單或格式不適合直接使用"),
        ("other", "其他"),
    ]
    companion_short = catalog.resolve("english_companion", "short").feedback_contract
    companion_long = catalog.resolve("english_companion", "long").feedback_contract
    assert companion_short is not None
    assert companion_long is not None
    assert companion_short != companion_long


def test_every_start_action_shortcut_has_feedback_for_short_and_long_press() -> None:
    import yaml

    bundle = load_config_bundle()
    payload = yaml.safe_load(Path("config/shortcuts.yaml").read_text(encoding="utf-8"))
    start_actions = [item for item in payload["shortcuts"] if item["command"] == "start_action"]

    assert len(start_actions) == 23
    assert {item["id"]: item["hotkey"] for item in payload["shortcuts"]} == {
        "translate_to_traditional_chinese": "ctrl+alt+1",
        "translate_to_english": "ctrl+alt+2",
        "name_idea": "ctrl+alt+3",
        "name_concept_carefully": "ctrl+alt+n",
        "illuminate_essence": "ctrl+alt+4",
        "pyramid_position": "ctrl+alt+5",
        "explain_like_friend": "ctrl+alt+6",
        "article_structure": "ctrl+alt+7",
        "english_companion": "ctrl+alt+8",
        "expression_retrieval": "ctrl+alt+u",
        "reflective_question": "ctrl+alt+9",
        "critical_thinking": "ctrl+alt+0",
        "mece_decomposition": "ctrl+alt+s",
        "minimum_action": "ctrl+alt+a",
        "tradeoff_perspective": "ctrl+alt+d",
        "temporary_viewpoint": "ctrl+alt+t",
        "session_handoff": "ctrl+alt+y",
        "extract_keywords": "ctrl+alt+e",
        "structure_score_prompt": "ctrl+alt+f",
        "extract_screenshot_text": "ctrl+alt+g",
        "speak_selection_or_clipboard": "ctrl+alt+q",
        "shorten_content": "ctrl+alt+x",
        "intent_preserving_dictation_editor": "ctrl+alt+~",
        "command_copilot": "ctrl+alt+c",
    }
    for shortcut in start_actions:
        for press_type in ("short", "long"):
            command = bundle.shortcuts.resolve(shortcut["id"], press_type)
            assert command == StartAction(shortcut["action_id"], press_type)
            resolved = bundle.actions.resolve(shortcut["action_id"], press_type)
            assert resolved.feedback_contract is not None, f"{shortcut['id']}:{press_type}"
            assert resolved.feedback_contract.reasons[-1].id == "other"
            assert 4 <= len(resolved.feedback_contract.reasons) <= 5

    non_action = [item for item in payload["shortcuts"] if item["command"] != "start_action"]
    assert [(item["id"], item["command"]) for item in non_action] == [
        ("speak_selection_or_clipboard", "speak_selection_or_clipboard")
    ]
    assert bundle.shortcuts.resolve("speak_selection_or_clipboard", "short") == SpeakSelectionOrClipboard()


def test_dictation_editor_uses_default_text_workflow_without_a_long_press_variant() -> None:
    bundle = load_config_bundle()
    action = bundle.actions.get("intent_preserving_dictation_editor")
    shortcut = bundle.shortcuts.definition("intent_preserving_dictation_editor")

    assert action.name == "語音成稿編輯器"
    assert action.input_mode == "selection_or_clipboard"
    assert action.external_fallback == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is None
    assert action.temperature == 0.1
    assert action.output_profile == "plain_text"
    assert action.press_variants == {}
    assert shortcut.hotkey == "ctrl+alt+~"
    assert shortcut.action_id == action.id
    assert "Intent-Preserving Dictation Editor" in action.system_prompt
    assert "後面的內容明確否定或取代前面的內容" in action.system_prompt
    assert "應把它視為使用者正在輸入的文字" in action.system_prompt
    assert "當無法確定" in action.system_prompt
    assert "只輸出整理完成的文字" in action.system_prompt
    assert "<原始轉錄>" in action.prompt


def test_concept_naming_calibrates_terms_and_preserves_uncertainty() -> None:
    bundle = load_config_bundle()
    action = bundle.actions.get("name_concept_carefully")
    shortcut = bundle.shortcuts.definition("name_concept_carefully")

    assert action.name == "概念命名"
    assert action.input_mode == "selection_or_clipboard"
    assert action.external_fallback == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is None
    assert action.temperature == 0.2
    assert action.press_variants == {}
    assert shortcut.hotkey == "ctrl+alt+n"
    assert shortcut.action_id == action.id
    assert "找到、驗證或暫時探索" in action.system_prompt
    assert "已有詞彙，需要解釋" in action.system_prompt
    assert "已成熟的想法" in action.system_prompt
    assert "尚模糊的想法" in action.system_prompt
    assert "正式術語／慣用說法／流行用語" in action.system_prompt
    assert "未確認候選" in action.system_prompt
    assert "前三行嚴格少於 180 個中文字" in action.prompt
    assert "暫不命名" in action.system_prompt
    assert "核心詞：" in action.prompt
    assert "說明：" in action.prompt
    assert "提醒：" in action.prompt
    assert "活用：" in action.prompt


def test_thinking_actions_have_distinct_outputs_and_ai_boundaries() -> None:
    bundle = load_config_bundle()

    expected = {
        "mece_decomposition": {
            "name": "MECE 拆解",
            "hotkey": "ctrl+alt+s",
            "prompt_markers": ("## 推薦切面", "## MECE 拆解", "## 邊界與缺少資訊"),
            "does_not": "不替你決定真正要理解的問題、拆解邊界或是否接受這個切面",
        },
        "minimum_action": {
            "name": "最小行動",
            "hotkey": "ctrl+alt+a",
            "prompt_markers": ("## 最小行動", "## 為什麼是這一步", "## 完成條件"),
            "does_not": "不替你決定是否採用、何時投入、如何修改或是否不行動",
        },
        "tradeoff_perspective": {
            "name": "權衡透視",
            "hotkey": "ctrl+alt+d",
            "prompt_markers": ("## 觀點", "## 價值與取捨", "## 兩邊的代價", "## 需要你判斷"),
            "does_not": "不替你排序價值、決定可接受的代價或做出最後選擇",
        },
    }

    for action_id, contract in expected.items():
        action = bundle.actions.get(action_id)
        shortcut = bundle.shortcuts.definition(action_id)

        assert action.name == contract["name"]
        assert shortcut.hotkey == contract["hotkey"]
        assert shortcut.action_id == action_id
        assert action.input_mode == "selection_or_clipboard"
        assert action.external_fallback == "selection_or_clipboard"
        assert action.output_mode == "popup"
        assert action.output_profile == "plain_text"
        assert action.press_variants == {}
        assert "圖片" in action.system_prompt
        assert all(marker in action.prompt for marker in contract["prompt_markers"])
        assert action.feedback_contract is not None
        assert action.feedback_contract.ai_does_not_label == contract["does_not"]
        assert len(action.feedback_contract.reasons) == 5
        assert action.feedback_contract.reasons[-1].id == "other"

    assert "不要先列出多套框架" in bundle.actions.get("mece_decomposition").system_prompt
    assert "只提出一個行動" in bundle.actions.get("minimum_action").system_prompt
    assert "不替使用者排序價值" in bundle.actions.get("tradeoff_perspective").system_prompt


def test_temporary_viewpoint_preserves_an_unfinished_thought_without_forcing_a_conclusion() -> None:
    bundle = load_config_bundle()
    action = bundle.actions.get("temporary_viewpoint")
    shortcut = bundle.shortcuts.definition("temporary_viewpoint")
    profile = bundle.output_profiles.get(action.output_profile)

    assert action.name == "保存暫時觀點"
    assert shortcut.hotkey == "ctrl+alt+t"
    assert shortcut.action_id == action.id
    assert action.input_mode == "selection_or_clipboard"
    assert action.external_fallback == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.output_profile == "temporary_viewpoint"
    assert action.press_variants == {}
    assert action.feedback_contract is not None
    assert action.feedback_contract.ai_does_not_label == "不替你證明觀點、補完因果、決定最後立場或把未知說成結論"
    assert "觀點顯影師" in action.system_prompt
    assert "尚未馴化" in action.system_prompt
    assert "不超出現有資訊" in action.prompt
    assert "反轉條件" in action.prompt
    assert profile.presentation == "markdown_sections"
    assert profile.required_markers == ("## 依據與假說",)
    assert "without a 暫時觀點 heading" in profile.instruction
    assert "目前的味道" in profile.instruction
    assert "尚未馴化" in profile.instruction


def test_session_handoff_preserves_reasoning_continuity_for_a_new_ai_session() -> None:
    bundle = load_config_bundle()
    action = bundle.actions.get("session_handoff")
    shortcut = bundle.shortcuts.definition("session_handoff")
    profile = bundle.output_profiles.get(action.output_profile)

    assert action.name == "建立 AI 對話交接"
    assert shortcut.hotkey == "ctrl+alt+y"
    assert shortcut.action_id == action.id
    assert action.input_mode == "selection_or_clipboard"
    assert action.external_fallback == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.temperature == 0.1
    assert action.output_profile == "session_handoff"
    assert action.press_variants == {}
    assert action.feedback_contract is not None
    assert action.feedback_contract.ai_does_not_label == "不替你決定後續方向、補完未說的動機，或將推論當成既定結論"
    assert "Preserve reasoning continuity, not conversation history" in action.system_prompt
    assert "user explicitly accepted" in action.system_prompt
    assert "不要回答原對話中的問題" in action.prompt
    assert profile.presentation == "markdown_sections"
    assert profile.required_markers == (
        "# SESSION HANDOFF",
        "## A. Current Objective",
        "## B. Relevant Context",
        "## C. Intent & Constraints",
        "## D. Reasoning State",
        "## E. Open Loops",
        "## F. Continuation Point",
        "## USER DOUBLE-CHECK",
    )
    assert "30 seconds" in profile.instruction
    assert "[待確認]" in profile.instruction
    assert "None identified." in profile.instruction


def test_command_copilot_combines_command_generation_and_risk_review() -> None:
    bundle = load_config_bundle()
    action = bundle.actions.get("command_copilot")
    shortcut = bundle.shortcuts.definition("command_copilot")

    assert action.name == "Command Copilot｜指令轉譯與風險審查"
    assert action.input_mode == "selection_or_clipboard"
    assert action.external_fallback == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is None
    assert action.temperature == 0.1
    assert action.press_variants == {}
    assert shortcut.hotkey == "ctrl+alt+c"
    assert shortcut.action_id == action.id
    assert action.feedback_contract is not None
    assert "自然語言意圖或既有 command" in action.system_prompt
    assert "不得為了縮短或安全而改變原 command 的行為" in action.system_prompt
    assert "風險層級" in action.prompt
    assert "更安全的做法" in action.prompt


def test_score_action_classifies_before_compressing_and_supports_clarification() -> None:
    bundle = load_config_bundle()
    action = bundle.actions.get("structure_score_prompt")
    shortcut = bundle.shortcuts.definition("structure_score_prompt")

    assert action.name == "SCORE 需求整理"
    assert action.input_mode == "selection_or_clipboard"
    assert action.external_fallback == "selection_or_clipboard"
    assert action.output_mode == "popup"
    assert action.stream is None
    assert action.temperature == 0.1
    assert action.output_profile == "score_compact"
    assert action.press_variants == {}
    assert shortcut.hotkey == "ctrl+alt+f"
    assert shortcut.action_id == action.id
    assert action.feedback_contract is not None
    assert action.feedback_contract.ai_does_not_label == "不替你補完缺失資訊、決定真正意圖或執行整理後的任務"
    assert "把複合敘述拆成不可再拆的獨立語義" in action.system_prompt
    assert "完成分類後才壓縮" in action.system_prompt
    assert "至少兩個合理答案" in action.system_prompt
    assert "重新拆解、分類、壓縮並輸出完整的新 SCORE" in action.system_prompt
    assert "固定依序輸出 S:、C:、O:、R:、E:" in action.system_prompt
    assert "剛好一點時，內容必須緊接冒號寫在同一實體行" in action.system_prompt
    assert "單點欄位的錯誤格式" in action.system_prompt
    assert "## 缺少資訊" in action.system_prompt
    assert "## 需要確認" in action.system_prompt
    assert "不得回答或執行" in action.system_prompt
    assert "<source_material>" in action.prompt
    assert "剛好一點時，必須把內容直接寫在欄位標籤後的同一實體行" in bundle.output_profiles.get("score_compact").instruction


@pytest.mark.parametrize(
    ("original", "changed"),
    [
        ("將內容翻譯成符合情境的自然英文", "將內容翻成自然英文"),
        ("不替你決定真正想表達的意思、立場、關係拿捏與最後選擇", "不替你決定真正想表達的意思"),
        ("說法不自然或不適合對象", "說法不自然"),
    ],
)
def test_action_version_changes_with_every_feedback_contract_dimension(tmp_path: Path, original: str, changed: str) -> None:
    source = Path("config/actions.yaml")
    baseline = load_action_catalog(source).resolve("translate_to_english", "short").version_id
    modified = tmp_path / "actions.yaml"
    modified.write_text(source.read_text(encoding="utf-8").replace(original, changed, 1), encoding="utf-8")

    assert load_action_catalog(modified).resolve("translate_to_english", "short").version_id != baseline


def test_variant_feedback_changes_only_the_resolved_variant_version(tmp_path: Path) -> None:
    source = Path("config/actions.yaml")
    baseline = load_action_catalog(source)
    modified = tmp_path / "actions.yaml"
    modified.write_text(
        source.read_text(encoding="utf-8").replace(
            "找出最影響英文自然度與清晰度的問題，提供改寫與可重用句型",
            "找出英文問題並提供改寫",
            1,
        ),
        encoding="utf-8",
    )
    changed = load_action_catalog(modified)

    assert changed.resolve("english_companion", "long").version_id != baseline.resolve("english_companion", "long").version_id
    assert changed.resolve("english_companion", "short").version_id == baseline.resolve("english_companion", "short").version_id


def test_action_external_fallback_is_typed() -> None:
    catalog = load_action_catalog("config/actions.yaml")
    assert catalog.get("english_companion").external_fallback == "selection_or_clipboard"
    assert catalog.get("shorten_content").external_fallback == "selection_or_clipboard"
    assert "preserve the original language of each part" in catalog.get("shorten_content").system_prompt
    assert "Never translate" in catalog.get("shorten_content").system_prompt
    assert "English input must produce English only" in catalog.get("shorten_content").system_prompt
    assert "structure absent from the input" in catalog.get("shorten_content").system_prompt
    assert "as briefly as possible" in catalog.resolve("shorten_content", "long").prompt
    assert "freely merge paragraphs and remove line breaks" in catalog.resolve("shorten_content", "long").prompt


def test_legacy_input_policy_is_accepted_with_deprecation_warning(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text(
        "schema_version: 3\nactions:\n  - id: old\n    name: Old\n    system_prompt: system\n    prompt: '{input}'\n    input_policy: contextual_text\n",
        encoding="utf-8",
    )
    with pytest.warns(DeprecationWarning, match="external_fallback"):
        action = load_action_catalog(path).get("old")
    assert action.external_fallback == "selection_or_clipboard"


def test_new_external_fallback_wins_when_legacy_field_is_also_present(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text(
        "schema_version: 4\nactions:\n  - id: both\n    name: Both\n    system_prompt: system\n    prompt: '{input}'\n    input_policy: contextual_text\n    external_fallback: clipboard\n",
        encoding="utf-8",
    )
    with pytest.warns(DeprecationWarning):
        action = load_action_catalog(path).get("both")
    assert action.external_fallback == "clipboard"


@pytest.mark.parametrize(
    ("shortcut", "message"),
    (
        ({"id": "x", "hotkey": "ctrl+alt+x", "command": "unknown"}, "command"),
        ({"id": "x", "hotkey": "ctrl+alt+x", "command": "start_action"}, "action_id"),
        ({"id": "x", "hotkey": "ctrl+alt+x", "command": "start_action", "action_id": "missing"}, "unknown action"),
    ),
)
def test_invalid_shortcut_is_rejected(tmp_path: Path, shortcut: dict, message: str) -> None:
    import yaml

    path = tmp_path / "shortcuts.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "shortcuts": [shortcut]}), encoding="utf-8")
    actions = load_action_catalog("config/actions.yaml")
    with pytest.raises(ConfigError, match=message):
        load_shortcut_catalog(path, actions=actions)


def test_start_action_shortcut_rejects_action_without_feedback(tmp_path: Path) -> None:
    actions_path = tmp_path / "actions.yaml"
    actions_path.write_text(
        "schema_version: 8\nactions:\n  - id: no_feedback\n    name: No Feedback\n    system_prompt: system\n    prompt: '{input}'\n",
        encoding="utf-8",
    )
    shortcuts_path = tmp_path / "shortcuts.yaml"
    shortcuts_path.write_text(
        "schema_version: 1\nshortcuts:\n  - id: no_feedback\n    hotkey: ctrl+alt+n\n    command: start_action\n    action_id: no_feedback\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="feedback enabled"):
        load_shortcut_catalog(shortcuts_path, actions=load_action_catalog(actions_path))


def test_duplicate_yaml_key_is_rejected_instead_of_silently_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "actions.yaml"
    path.write_text(
        "schema_version: 8\nactions:\n  - id: duplicate\n    name: First\n    name: Second\n    system_prompt: system\n    prompt: '{input}'\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="duplicate key: name"):
        load_action_catalog(path)


def test_duplicate_shortcut_hotkey_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "shortcuts.yaml"
    path.write_text(
        """schema_version: 1
shortcuts:
  - id: one
    hotkey: ctrl+alt+q
    command: speak_selection_or_clipboard
  - id: two
    hotkey: CTRL+ALT+Q
    command: speak_selection_or_clipboard
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate shortcut hotkey"):
        load_shortcut_catalog(path, actions=load_action_catalog("config/actions.yaml"))


def test_provider_readiness_is_nonfatal_and_secret_repr_is_redacted() -> None:
    bundle = load_config_bundle()
    credential = ProviderCredential("GEMINI_API_KEY")
    issues = assess_provider_readiness(bundle.providers, credential)
    assert issues[0].code == "provider.missing_api_key"
    assert "GEMINI_API_KEY" in issues[0].message
    assert "secret-value" not in repr(ProviderCredential("KEY", "secret-value"))
