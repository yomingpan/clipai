from __future__ import annotations

import contextlib
import contextvars
import logging
import os
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s%(log_context)s: %(message)s"
DEFAULT_LOG_PROFILE = "production"
DEFAULT_LOG_LEVEL = "INFO"

_diagnostics: dict[str, bool] = {
    "hotkey_raw_events": False,
    "selection_capture_polls": False,
    "paste_timing": False,
}
_profile_defaults: dict[str, dict[str, Any]] = {
    "production": {
        "console_level": "INFO",
        "file_level": "DEBUG",
        "diagnostics": {
            "hotkey_raw_events": False,
            "selection_capture_polls": False,
            "paste_timing": False,
        },
    },
    "diagnostics": {
        "console_level": "DEBUG",
        "file_level": "DEBUG",
        "diagnostics": {
            "hotkey_raw_events": True,
            "selection_capture_polls": True,
            "paste_timing": True,
        },
    },
}
_context_action_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("clipai_action_id", default=None)
_context_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("clipai_correlation_id", default=None)
_configured_logger_names: set[str] = set()


class _ClipAILogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        action_id = getattr(record, "action_id", None) or _context_action_id.get()
        correlation_id = getattr(record, "correlation_id", None) or _context_correlation_id.get()
        record.action_id = action_id or "-"
        record.correlation_id = correlation_id or "-"

        parts: list[str] = []
        if correlation_id:
            parts.append(f"corr={correlation_id}")
        if action_id:
            parts.append(f"action={action_id}")
        record.log_context = f" [{' '.join(parts)}]" if parts else ""
        return True


def _resolve_level(level_name: str | None, fallback: int) -> int:
    if not level_name:
        return fallback
    return getattr(logging, str(level_name).upper(), fallback)


def setup_logging(config: dict[str, Any] | None = None) -> None:
    logging_cfg = dict((config or {}).get("logging") or {})
    enabled = bool(logging_cfg.get("enabled", True))
    profile_name = str(logging_cfg.get("profile") or DEFAULT_LOG_PROFILE).lower()
    profile = _profile_defaults.get(profile_name, _profile_defaults[DEFAULT_LOG_PROFILE])
    default_level = _resolve_level(str(logging_cfg.get("level") or DEFAULT_LOG_LEVEL), logging.INFO)
    console_level = _resolve_level(logging_cfg.get("console_level"), _resolve_level(profile.get("console_level"), default_level))
    file_level = _resolve_level(logging_cfg.get("file_level"), _resolve_level(profile.get("file_level"), default_level))

    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if enabled else logging.CRITICAL + 1)

    formatter = logging.Formatter(LOG_FORMAT)
    context_filter = _ClipAILogContextFilter()

    if enabled and bool(logging_cfg.get("console", True)):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level)
        console_handler.addFilter(context_filter)
        root.addHandler(console_handler)

    if enabled and bool(logging_cfg.get("file_enabled", True)):
        file_path = str(logging_cfg.get("file_path") or "logs/clipai.log")
        path = Path(file_path)
        if path.parent:
            os.makedirs(path.parent, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(file_level)
        file_handler.addFilter(context_filter)
        root.addHandler(file_handler)

    for logger_name in list(_configured_logger_names):
        logging.getLogger(logger_name).setLevel(logging.NOTSET)
    _configured_logger_names.clear()

    module_levels = dict(logging_cfg.get("module_levels") or {})
    for logger_name, configured_level in module_levels.items():
        logger = logging.getLogger(str(logger_name))
        logger.setLevel(_resolve_level(str(configured_level), default_level))
        _configured_logger_names.add(str(logger_name))

    diagnostics = dict(profile.get("diagnostics") or {})
    diagnostics.update(dict(logging_cfg.get("diagnostics") or {}))
    for key in list(_diagnostics):
        _diagnostics[key] = bool(diagnostics.get(key, False))


def diagnostics_enabled(flag: str) -> bool:
    return bool(_diagnostics.get(flag, False))


def new_correlation_id() -> str:
    return uuid4().hex[:8]


@contextlib.contextmanager
def logging_context(*, action_id: str | None = None, correlation_id: str | None = None) -> Iterator[None]:
    action_token = None
    correlation_token = None
    if action_id is not None:
        action_token = _context_action_id.set(action_id)
    if correlation_id is not None:
        correlation_token = _context_correlation_id.set(correlation_id)
    try:
        yield
    finally:
        if correlation_token is not None:
            _context_correlation_id.reset(correlation_token)
        if action_token is not None:
            _context_action_id.reset(action_token)
