from __future__ import annotations

import multiprocessing

from ClipAI.app.application_lifecycle import build_application_instance_gate
from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.container import build_runtime
from ClipAI.core.errors import ConfigError
from ClipAI.core.ports import ApplicationInstanceGate
from ClipAI.ui.startup_error import show_startup_error

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def main(*, instance_gate: ApplicationInstanceGate | None = None) -> None:
    instance_gate = instance_gate or build_application_instance_gate()
    instance_lease = instance_gate.acquire()
    if instance_lease is None:
        show_startup_error("ClipAI is already running.")
        return
    try:
        if load_dotenv:
            load_dotenv(override=True)

        bundle = load_config_bundle()
        runtime = build_runtime(bundle)
        runtime.run_forever()
    except ConfigError as exc:
        show_startup_error(str(exc))
        raise SystemExit(2) from None
    finally:
        if instance_lease is not None:
            instance_lease.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
