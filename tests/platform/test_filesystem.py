from __future__ import annotations

import json
from pathlib import Path

from ClipAI.platform.filesystem import JsonlArchiveStore


def test_archive_store_appends_utf8_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "archive.jsonl"
    store = JsonlArchiveStore(path)
    store.save("第一筆")
    store.save("second")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["text"] for record in records] == ["第一筆", "second"]
    assert all(record["created_at"] for record in records)

