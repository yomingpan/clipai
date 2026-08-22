from __future__ import annotations

import json

from ClipAI.core.models import PersonalStyleCollection, PersonalStyleProfile
from ClipAI.platform.personal_styles import JsonPersonalStyleStore, Utf8PersonalStyleFileReader


def test_personal_style_store_round_trips_atomically(tmp_path) -> None:
    path = tmp_path / "data" / "personal_styles.json"
    store = JsonPersonalStyleStore(path)
    collection = PersonalStyleCollection(
        (PersonalStyleProfile("one", "Yoming", "只改怎麼說。", "ignored-on-load"),),
        "one",
    )

    store.save(collection)

    loaded = store.load()
    assert loaded.profiles[0].profile_id == "one"
    assert loaded.profiles[0].name == "Yoming"
    assert loaded.profiles[0].guide == "只改怎麼說。"
    assert loaded.profiles[0].content_hash != "ignored-on-load"
    assert loaded.selected_profile_id == "one"
    assert list(path.parent.glob("*.tmp")) == []
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_invalid_personal_style_store_falls_back_safely(tmp_path) -> None:
    path = tmp_path / "personal_styles.json"
    path.write_text('{"schema_version": 2}', encoding="utf-8")
    assert JsonPersonalStyleStore(path).load() == PersonalStyleCollection()


def test_personal_style_reader_accepts_utf8_bom(tmp_path) -> None:
    path = tmp_path / "style.md"
    path.write_bytes(b"\xef\xbb\xbf# Style\nwords")
    assert Utf8PersonalStyleFileReader().read_text(str(path)) == "# Style\nwords"
