from __future__ import annotations

import logging
from pathlib import Path

from clipai.logging_setup import diagnostics_enabled, setup_logging


def test_setup_logging_applies_root_and_module_levels(tmp_path: Path) -> None:
    log_path = tmp_path / "clipai.log"
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "level": "WARNING",
                "console": False,
                "file_enabled": True,
                "file_path": str(log_path),
                "module_levels": {
                    "clipai.hotkey": "INFO",
                },
                "diagnostics": {
                    "hotkey_raw_events": True,
                },
            }
        }
    )

    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("clipai.hotkey").level == logging.INFO
    assert diagnostics_enabled("hotkey_raw_events") is True
    assert log_path.exists()


def test_setup_logging_defaults_disable_diagnostics_flags(tmp_path: Path) -> None:
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "console": False,
                "file_enabled": True,
                "file_path": str(tmp_path / "clipai.log"),
            }
        }
    )

    assert diagnostics_enabled("hotkey_raw_events") is False
    assert diagnostics_enabled("selection_capture_polls") is False
    assert diagnostics_enabled("paste_timing") is False
