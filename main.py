from __future__ import annotations

import logging
import multiprocessing
import traceback
from datetime import datetime
from pathlib import Path

from clipai.app.config import load_app_config
from clipai.app.runtime import DesktopRuntime
from clipai.logging_setup import setup_logging
from clipai.platform.notification import notify

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

logger = logging.getLogger("clipai")
BASE_DIR = Path(__file__).resolve().parent
STARTUP_LOG_PATH = BASE_DIR / "logs" / "startup.log"


def _append_startup_log(message: str) -> None:
    STARTUP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with STARTUP_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} {message}\n")


def main() -> None:
    try:
        if load_dotenv:
            load_dotenv()

        bundle = load_app_config("config/config.yaml")
        setup_logging(bundle.cfg)
        logger.info("[clipai] Starting desktop runtime...")
        _append_startup_log("[clipai] Startup begin")
        runtime = DesktopRuntime(bundle)
        runtime.start()
        runtime.run_forever()
    except Exception as exc:
        details = "".join(traceback.format_exception(exc))
        _append_startup_log(f"[clipai] Startup failed: {exc}\n{details}")
        try:
            logger.exception("[clipai] Unhandled startup error: %s", exc)
        except Exception:
            pass
        try:
            notify("ClipAI", f"Startup failed: {exc}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
