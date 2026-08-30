from ClipAI.core.models import EntryActionRef
from ClipAI.services.recent_actions import RecentActionHistory


def test_recent_actions_are_unique_by_action_and_keep_latest_press_type() -> None:
    history = RecentActionHistory((
        EntryActionRef("english_companion", "short"),
        EntryActionRef("shorten_content", "short"),
        EntryActionRef("critical_thinking", "short"),
    ))

    refs = history.record(EntryActionRef("shorten_content", "long"))

    assert refs == (
        EntryActionRef("shorten_content", "long"),
        EntryActionRef("english_companion", "short"),
        EntryActionRef("critical_thinking", "short"),
    )
