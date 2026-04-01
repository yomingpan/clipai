from __future__ import annotations

import logging
import multiprocessing

from clipai.app.config import load_app_config
from clipai.app.runtime import DesktopRuntime

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

logger = logging.getLogger("clipai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    logger.info("[clipai] Starting desktop runtime...")

    if load_dotenv:
        load_dotenv()

    bundle = load_app_config("config/config.yaml")
    runtime = DesktopRuntime(bundle)
    runtime.start()
    runtime.run_forever()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
