from __future__ import annotations

import multiprocessing

from ClipAI.app.config import load_config_bundle
from ClipAI.app.runtime import Phase3Runtime

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def main() -> None:
    if load_dotenv:
        load_dotenv()

    bundle = load_config_bundle()
    runtime = Phase3Runtime(bundle)
    runtime.start()
    runtime.run_forever()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
