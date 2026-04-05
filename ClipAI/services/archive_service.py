from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clipai.services.popup_session import PopupSession


class ArchiveService:
    def __init__(self, path: str = "logs/popup_archive.jsonl", output_dir: str = "output/archive") -> None:
        self._path = path
        self._output_dir = output_dir

    def append_session(self, session: PopupSession) -> str:
        record = self._session_record(session)
        self.append_record(record)
        return self._write_output_file(record)

    def append_text(self, session: PopupSession, text: str) -> str:
        record = self._session_record(session, latest_result=text, selection_only=True)
        self.append_record(record)
        return self._write_output_file(record)

    def append_record(self, record: dict[str, Any]) -> None:
        folder = os.path.dirname(self._path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_output_file(self, record: dict[str, Any]) -> str:
        Path(self._output_dir).mkdir(parents=True, exist_ok=True)
        filename = self._build_filename(record)
        path = os.path.join(self._output_dir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self._render_markdown(record))
        return path

    @staticmethod
    def _session_record(
        session: PopupSession,
        *,
        latest_result: str | None = None,
        selection_only: bool = False,
    ) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "action_id": session.action_id,
            "action_name": session.action_name,
            "original_input": session.original_input,
            "latest_result": session.latest_result if latest_result is None else latest_result,
            "selection_only": selection_only,
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

    @staticmethod
    def _build_filename(record: dict[str, Any]) -> str:
        stamp = record.get("archived_at", "").replace(":", "-")
        stamp = stamp.split(".")[0].replace("+00-00", "Z")
        action_name = str(record.get("action_name") or record.get("action_id") or "clipai")
        safe_action = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in action_name).strip("_")
        safe_action = safe_action or "clipai"
        session_id = str(record.get("session_id") or "session")[:8]
        return f"{stamp}_{safe_action}_{session_id}.md"

    @staticmethod
    def _render_markdown(record: dict[str, Any]) -> str:
        lines = [
            f"# {record.get('action_name') or record.get('action_id') or 'ClipAI Archive'}",
            "",
            f"- Session: `{record.get('session_id', '')}`",
            f"- Action: `{record.get('action_id', '')}`",
            f"- Archived At: `{record.get('archived_at', '')}`",
            f"- Scope: `{'selection' if record.get('selection_only') else 'full_output'}`",
            "",
            "## Analysis",
            "",
            str(record.get("original_input") or "").strip() or "(empty input)",
            "",
            "## Result",
            "",
            str(record.get("latest_result") or "").strip() or "(empty result)",
        ]

        rounds = record.get("rounds") or []
        if rounds:
            lines.extend(["", "## Follow-up History", ""])
            for item in rounds:
                lines.extend(
                    [
                        f"### Round {item.get('round_index', '?')} - {item.get('kind', 'follow_up')}",
                        "",
                        f"Prompt: {item.get('prompt_text', '').strip()}",
                        "",
                        str(item.get("result_text") or "").strip() or "(empty result)",
                        "",
                    ]
                )
        return "\n".join(lines).rstrip() + "\n"
