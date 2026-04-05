from __future__ import annotations

import logging
from pathlib import Path

from clipai.logging_setup import diagnostics_enabled, logging_context, setup_logging


def test_setup_logging_production_profile_uses_dual_handler_levels(tmp_path: Path) -> None:
    log_path = tmp_path / "clipai.log"
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "profile": "production",
                "console": True,
                "file_enabled": True,
                "file_path": str(log_path),
                "module_levels": {
                    "clipai.hotkey": "INFO",
                },
            }
        }
    )

    root = logging.getLogger()
    file_handlers = [handler for handler in root.handlers if isinstance(handler, logging.FileHandler)]
    stream_handlers = [handler for handler in root.handlers if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)]

    assert root.level == logging.DEBUG
    assert stream_handlers and stream_handlers[0].level == logging.INFO
    assert file_handlers and file_handlers[0].level == logging.DEBUG
    assert logging.getLogger("clipai.hotkey").level == logging.INFO
    assert diagnostics_enabled("hotkey_raw_events") is False
    assert diagnostics_enabled("selection_capture_polls") is False
    assert diagnostics_enabled("paste_timing") is False
    assert log_path.exists()


def test_setup_logging_diagnostics_profile_enables_debug_defaults(tmp_path: Path) -> None:
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "profile": "diagnostics",
                "console": True,
                "file_enabled": True,
                "file_path": str(tmp_path / "clipai.log"),
            }
        }
    )

    root = logging.getLogger()
    file_handlers = [handler for handler in root.handlers if isinstance(handler, logging.FileHandler)]
    stream_handlers = [handler for handler in root.handlers if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)]

    assert root.level == logging.DEBUG
    assert stream_handlers and stream_handlers[0].level == logging.DEBUG
    assert file_handlers and file_handlers[0].level == logging.DEBUG
    assert diagnostics_enabled("hotkey_raw_events") is True
    assert diagnostics_enabled("selection_capture_polls") is True
    assert diagnostics_enabled("paste_timing") is True


def test_logging_context_writes_correlation_id_and_action_id(tmp_path: Path) -> None:
    log_path = tmp_path / "clipai.log"
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "profile": "production",
                "console": False,
                "file_enabled": True,
                "file_path": str(log_path),
            }
        }
    )

    logger = logging.getLogger("clipai.action_runner")
    with logging_context(action_id="translate_en", correlation_id="corr1234"):
        logger.info("[clipai] Run start")

    content = log_path.read_text(encoding="utf-8")
    assert "corr=corr1234" in content
    assert "action=translate_en" in content
    assert "[clipai] Run start" in content


def test_setup_logging_with_console_disabled_skips_stream_handler(tmp_path: Path) -> None:
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "profile": "production",
                "console": False,
                "file_enabled": True,
                "file_path": str(tmp_path / "clipai.log"),
            }
        }
    )

    root = logging.getLogger()
    file_handlers = [handler for handler in root.handlers if isinstance(handler, logging.FileHandler)]
    stream_handlers = [handler for handler in root.handlers if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)]

    assert file_handlers
    assert not stream_handlers
