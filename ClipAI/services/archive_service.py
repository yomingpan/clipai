from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from clipai.services.popup_session import PopupSession


class ArchiveService:
    def __init__(self, path: str = "logs/popup_archive.jsonl") -> None:
        self._path = path

    def append_session(self, session: PopupSession) -> None:
        self.append_record(
            {
                "session_id": session.session_id,
                "action_id": session.action_id,
                "action_name": session.action_name,
                "original_input": session.original_input,
                "latest_result": session.latest_result,
                "round_count": session.round_count,
                "max_rounds": session.max_rounds,
                "rounds": [
                    {
                        "round_index": item.round_index,
                        "kind": item.kind,
                        "prompt_text": item.prompt_text,
                        "result_text": item.result_text,
                        "model": item.model,
                        "created_at": item.created_at,
                    }
                    for item in session.rounds
                ],
                "archived_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def append_record(self, record: dict[str, Any]) -> None:
        folder = os.path.dirname(self._path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
