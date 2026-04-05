from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DEFAULT_LOG_LEVEL = "INFO"

_diagnostics: dict[str, bool] = {
    "hotkey_raw_events": False,
    "selection_capture_polls": False,
    "paste_timing": False,
}


def setup_logging(config: dict[str, Any] | None = None) -> None:
    logging_cfg = dict((config or {}).get("logging") or {})
    enabled = bool(logging_cfg.get("enabled", True))
    level_name = str(logging_cfg.get("level") or DEFAULT_LOG_LEVEL).upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level if enabled else logging.CRITICAL + 1)

    formatter = logging.Formatter(LOG_FORMAT)

    if enabled and bool(logging_cfg.get("console", True)):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    if enabled and bool(logging_cfg.get("file_enabled", True)):
        file_path = str(logging_cfg.get("file_path") or "logs/clipai.log")
        path = Path(file_path)
        if path.parent:
            os.makedirs(path.parent, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    module_levels = dict(logging_cfg.get("module_levels") or {})
    for logger_name, configured_level in module_levels.items():
        logger = logging.getLogger(str(logger_name))
        logger.setLevel(getattr(logging, str(configured_level).upper(), level))

    diagnostics = dict(logging_cfg.get("diagnostics") or {})
    for key in list(_diagnostics):
        _diagnostics[key] = bool(diagnostics.get(key, False))


def diagnostics_enabled(flag: str) -> bool:
    return bool(_diagnostics.get(flag, False))
