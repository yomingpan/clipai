from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import platform
import re
import sys
import uuid
from zipfile import ZIP_DEFLATED, ZipFile


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|secret|cookie)(\s*[:=]\s*)([^\s,;]+)"
)


class IncidentReporter:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("clipai.incident")

    def report(self, error: BaseException, *, context: str) -> str:
        incident_id = uuid.uuid4().hex[:12]
        self._logger.error(
            "Unexpected error incident_id=%s context=%s",
            incident_id,
            context,
            exc_info=error,
        )
        return incident_id


class SafeDiagnosticsExporter:
    """Create a small diagnostics archive from explicitly curated metadata."""

    def __init__(
        self,
        *,
        metadata: Mapping[str, object],
        log_path: str | Path,
        output_dir: str | Path = "diagnostics",
        sensitive_values: Sequence[str] = (),
        now: Callable[[], datetime] | None = None,
        max_log_lines: int = 500,
    ) -> None:
        self._metadata = dict(metadata)
        self._log_path = Path(log_path)
        self._output_dir = Path(output_dir)
        self._sensitive_values = tuple(value for value in sensitive_values if value)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._max_log_lines = max_log_lines

    def export(self) -> Path:
        created_at = self._now().astimezone(timezone.utc)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        destination = self._output_dir / f"clipai-diagnostics-{created_at:%Y%m%d-%H%M%S}.zip"
        report = {
            "created_at": created_at.isoformat(),
            "application": self._metadata,
            "runtime": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "platform": platform.platform(),
                "executable_name": Path(sys.executable).name,
            },
        }
        with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("report.json", self._redact(json.dumps(report, ensure_ascii=False, indent=2)))
            archive.writestr("clipai.log", self._redact(self._read_log_tail()))
        return destination.resolve()

    def _read_log_tail(self) -> str:
        try:
            lines = self._log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return "Log file is not available.\n"
        return "\n".join(lines[-self._max_log_lines :]) + ("\n" if lines else "")

    def _redact(self, text: str) -> str:
        for value in sorted(self._sensitive_values, key=len, reverse=True):
            text = text.replace(value, "[REDACTED]")
        return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
