"""Exercise installed desktop startup and explicitly enqueue shutdown.

Does not configure providers, request AI, capture selection or mutate clipboard.
Uses the existing desktop instance gate; skips if the user's app is running.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import threading

import main as application
from ClipAI.app.application_lifecycle import build_application_instance_gate
from ClipAI.app.application_paths import build_managed_application_paths
from ClipAI.core.commands import ShutdownApplication


class AdmittedGate:
    def __init__(self, lease):
        self.lease = lease

    def acquire(self):
        return self.lease


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--shared-root", required=True, type=Path)
    args = parser.parse_args()
    lease = build_application_instance_gate().acquire()
    if lease is None:
        print("DESKTOP_STARTUP_SKIPPED_USER_APP_RUNNING", flush=True)
        return 2
    original = application.build_runtime
    runtime = None

    def build(*arguments, **keywords):
        nonlocal runtime
        runtime = original(*arguments, **keywords)
        return runtime

    def started():
        print("DESKTOP_RUNTIME_READY", flush=True)
        threading.Timer(3, lambda: runtime.enqueue(ShutdownApplication())).start()

    application.build_runtime = build
    try:
        paths = build_managed_application_paths(args.install_root / "versions/3.7.8/payload",
                                               args.shared_root, instance_name="default")
        application._run_application(paths, instance_gate=AdmittedGate(lease), on_started=started)
    finally:
        lease.close()
    print("DESKTOP_TYPED_SHUTDOWN_COMPLETED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
