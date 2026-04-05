from __future__ import annotations

import json
from pathlib import Path

from clipai.services.archive_service import ArchiveService
from clipai.services.popup_session import PopupSession


def test_archive_service_writes_markdown_and_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "popup_archive.jsonl"
    output_dir = tmp_path / "output"
    service = ArchiveService(path=str(log_path), output_dir=str(output_dir))
    session = PopupSession(
        action_id="summarize",
        action_name="Summarize",
        original_input="Original text",
        latest_result="Final result",
    )
    session.start_round(kind="follow_up", prompt_text="Refine it", model="gemini")
    session.mark_result_ready("Refined result")

    archive_path = service.append_session(session)

    assert Path(archive_path).exists()
    content = Path(archive_path).read_text(encoding="utf-8")
    assert "# Summarize" in content
    assert "## Result" in content
    assert "Refined result" in content

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["action_id"] == "summarize"
    assert payload["latest_result"] == "Refined result"


def test_archive_service_can_archive_selection_only_text(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "popup_archive.jsonl"
    output_dir = tmp_path / "output"
    service = ArchiveService(path=str(log_path), output_dir=str(output_dir))
    session = PopupSession(
        action_id="summarize",
        action_name="Summarize",
        original_input="Original text",
        latest_result="Full result",
    )

    archive_path = service.append_text(session, "Selected result")

    content = Path(archive_path).read_text(encoding="utf-8")
    assert "Selected result" in content
    assert "Full result" not in content
    assert "- Scope: `selection`" in content

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["latest_result"] == "Selected result"
    assert payload["selection_only"] is True
