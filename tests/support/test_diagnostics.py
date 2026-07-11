from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from zipfile import ZipFile

from ClipAI.support.diagnostics import IncidentReporter, SafeDiagnosticsExporter


def test_diagnostics_export_is_curated_and_redacts_secrets(tmp_path: Path) -> None:
    secret = "super-secret-value"
    log_path = tmp_path / "clipai.log"
    log_path.write_text(
        f"Authorization: Bearer {secret}\napi_key={secret}\nordinary diagnostic\n",
        encoding="utf-8",
    )
    exporter = SafeDiagnosticsExporter(
        metadata={"version": "3.0.1", "provider": "gemini", "ready": False},
        log_path=log_path,
        output_dir=tmp_path / "diagnostics",
        sensitive_values=(secret,),
        now=lambda: datetime(2026, 7, 11, 4, 0, tzinfo=timezone.utc),
    )

    destination = exporter.export()

    assert destination.name == "clipai-diagnostics-20260711-040000.zip"
    with ZipFile(destination) as archive:
        report = json.loads(archive.read("report.json"))
        logs = archive.read("clipai.log").decode("utf-8")
    assert report["application"] == {"version": "3.0.1", "provider": "gemini", "ready": False}
    assert secret not in logs
    assert "ordinary diagnostic" in logs
    assert "[REDACTED]" in logs


def test_diagnostics_export_tolerates_missing_log(tmp_path: Path) -> None:
    exporter = SafeDiagnosticsExporter(
        metadata={},
        log_path=tmp_path / "missing.log",
        output_dir=tmp_path,
        now=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    with ZipFile(exporter.export()) as archive:
        assert b"not available" in archive.read("clipai.log")


def test_incident_reporter_returns_short_reference(caplog) -> None:
    reporter = IncidentReporter()
    incident_id = reporter.report(RuntimeError("boom"), context="runtime")
    assert len(incident_id) == 12
    assert incident_id in caplog.text
