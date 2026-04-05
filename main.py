from __future__ import annotations

import logging
import multiprocessing

from clipai.app.config import load_app_config
from clipai.app.runtime import DesktopRuntime
from clipai.logging_setup import setup_logging

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

logger = logging.getLogger("clipai")


def main() -> None:
    if load_dotenv:
        load_dotenv()

    bundle = load_app_config("config/config.yaml")
    setup_logging(bundle.cfg)
    logger.info("[clipai] Starting desktop runtime...")
    runtime = DesktopRuntime(bundle)
    runtime.start()
    runtime.run_forever()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
