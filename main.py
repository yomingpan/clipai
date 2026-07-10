from __future__ import annotations

import multiprocessing

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.container import build_runtime

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def main() -> None:
    if load_dotenv:
        load_dotenv()

    bundle = load_config_bundle()
    runtime = build_runtime(bundle)
    runtime.run_forever()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
