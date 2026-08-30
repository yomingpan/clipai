import json

from ClipAI.core.models import EntryActionRef
from ClipAI.platform.recent_actions import JsonRecentActionStore


def test_recent_action_store_round_trips_only_replay_references(tmp_path) -> None:
    path = tmp_path / "recent-actions.json"
    store = JsonRecentActionStore(path)
    refs = (
        EntryActionRef("shorten_content", "long"),
        EntryActionRef("english_companion", "short"),
    )

    store.save(refs)

    assert store.load() == refs
    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"action_id": "shorten_content", "press_type": "long"},
        {"action_id": "english_companion", "press_type": "short"},
    ]


def test_recent_action_store_fails_closed_on_invalid_or_private_fields(tmp_path) -> None:
    path = tmp_path / "recent-actions.json"
    path.write_text(
        '[{"action_id":"shorten_content","press_type":"short","text":"private"}]',
        encoding="utf-8",
    )

    assert JsonRecentActionStore(path).load() == ()
