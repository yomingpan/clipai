from __future__ import annotations

import pytest

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.language_pack_loader import (
    ActionLanguagePackLoader,
    LanguagePackRegistryEntry,
    load_feature_skeleton,
)
from ClipAI.core.models import EntryActionRef
from ClipAI.services.entry_panel import EntryPanelCoordinator
from ClipAI.services.prompt_builder import PromptBuilder


@pytest.mark.parametrize("pack_id", ["zh-TW", "ja-JP"])
@pytest.mark.parametrize(
    "source",
    [
        "幫我看現在的 branch 跟 main 差了哪些檔案，不要改東西。",
        "參考 git diff main HEAD，改成只列檔名。",
        "比較那個檔案和另一個分支。",
        "PowerShell: D:\\Projects\\ClipAI v2; branch Feature/Popup; file src/{draft}.py",
    ],
)
def test_explicit_command_task_builds_distinct_requests_from_the_same_input(
    pack_id: str, source: str,
) -> None:
    loader = ActionLanguagePackLoader("config", load_feature_skeleton("config"))
    pack = loader.load(
        LanguagePackRegistryEntry(pack_id, f"language_packs/{pack_id}")
    )
    bundle = load_config_bundle(action_language_pack=pack)
    panel = EntryPanelCoordinator(bundle.entry_panel)
    panel.open("commands")
    tools = panel.select_digit("7").snapshot
    assert tools is not None
    selected = [
        option.action for option in tools.options
        if option.action is not None
        and option.action.action_id in ("command_copilot", "command_generate")
    ]
    more = panel.open_more()
    selected.extend(option.action for option in more.options if option.action is not None)
    assert set(selected) == {
        EntryActionRef("command_copilot", "short"),
        EntryActionRef("command_generate", "short"),
        EntryActionRef("command_coach", "short"),
    }

    builder = PromptBuilder(bundle.app.system_prompt, bundle.output_profiles)
    requests = []
    for reference in selected:
        action = bundle.actions.resolve(reference.action_id, reference.press_type)
        request = builder.build(
            action, source, model="test-model", default_temperature=0.9,
        )
        assert request.messages[0].role == "system"
        assert action.system_prompt in request.messages[0].content
        assert action.output_profile == "command_readable"
        profile = bundle.output_profiles.get(action.output_profile)
        assert profile.instruction in request.messages[0].content
        assert request.messages[1].role == "user"
        assert request.messages[1].content == action.prompt.format(input=source)
        assert request.messages[1].content.endswith(source)
        assert request.temperature == 0.1
        assert action.input_mode == "selection_or_clipboard"
        assert action.output_mode == "popup"
        assert action.feedback_contract is not None
        assert action.feedback_contract.ai_help_label
        assert action.feedback_contract.ai_does_not_label
        # Recent can replay every task, including coaching without a hotkey.
        assert bundle.entry_panel.recent_candidate_for_action(reference) is not None
        requests.append(request)

    assert len({request.messages[0].content for request in requests}) == 3
    assert len({request.messages[1].content for request in requests}) == 3
