from __future__ import annotations

import json
import os

import pytest

from ClipAI.core.errors import ActionLanguagePackError
from ClipAI.core.models import ActionLanguagePackSelectionRead
from ClipAI.platform.action_language_selection import (
    JsonActionLanguagePackSelectionStore,
)


def test_missing_selection_has_no_override_or_diagnostic(tmp_path) -> None:
    store = JsonActionLanguagePackSelectionStore(tmp_path / "selection.json")

    assert store.load() == ActionLanguagePackSelectionRead(None)


def test_selection_round_trips_only_schema_and_pack_id_atomically(tmp_path) -> None:
    path = tmp_path / "data" / "selection.json"
    store = JsonActionLanguagePackSelectionStore(path)

    store.save("ja-JP")

    assert store.load() == ActionLanguagePackSelectionRead("ja-JP")
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "selected_pack_id": "ja-JP",
    }
    assert tuple(path.parent.glob("*.tmp")) == ()


@pytest.mark.parametrize(
    "payload",
    (
        "[]",
        '{"schema_version":2,"selected_pack_id":"ja-JP"}',
        '{"schema_version":1,"selected_pack_id":"../escape"}',
        '{"schema_version":1,"selected_pack_id":"ja-JP","locale":"ja-JP"}',
        "not json",
    ),
)
def test_corrupt_or_future_selection_falls_back_with_safe_diagnostic(
    tmp_path,
    payload: str,
) -> None:
    path = tmp_path / "selection.json"
    path.write_text(payload, encoding="utf-8")

    selection = JsonActionLanguagePackSelectionStore(path).load()

    assert selection.selected_pack_id is None
    assert selection.diagnostic_code.startswith("action_language.selection_")


def test_failed_replace_raises_typed_failure_and_cleans_temporary_file(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "selection.json"
    store = JsonActionLanguagePackSelectionStore(path)
    monkeypatch.setattr(os, "replace", lambda *_args: (_ for _ in ()).throw(OSError()))

    with pytest.raises(ActionLanguagePackError) as caught:
        store.save("ja-JP")

    assert caught.value.reason == "selection_save_failed"
    assert tuple(tmp_path.glob("*.tmp")) == ()
