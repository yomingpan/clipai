"""Native managed health/console probe with explicit typed test shutdown.

Run only after the user exits ClipAI. Does not send provider requests or copy
credentials. The test entry wraps the admitted payload solely to schedule its
own shutdown and measure GetConsoleWindow at actual desktop readiness.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.platform.first_install_backend import read_owner
from ClipAI.platform.managed_install import ManagedInstallLayout
from ClipAI.platform.managed_update_lifecycle import SubprocessManagedApplicationLifecycle, start_detached_process
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, shared, out = args.install_root.resolve(), args.shared_root.resolve(), args.output.resolve()
    owner = read_owner(root, shared)
    out.mkdir(parents=True, exist_ok=False)
    report, helper = out / "desktop.json", out / "entry.py"
    helper.write_text('''import sys,runpy,threading,json,ctypes
from pathlib import Path
from ClipAI.app.runtime import AppRuntime
from ClipAI.core.commands import ShutdownApplication
original=AppRuntime.run_forever
def run(self,*,on_started=None):
 def ready():
  ctypes.windll.kernel32.GetConsoleWindow.restype=ctypes.c_void_p
  Path(REPORT).write_text(json.dumps({"console_present":bool(ctypes.windll.kernel32.GetConsoleWindow()),"runtime_ready":True}))
  if on_started:on_started()
  threading.Timer(3,lambda:self.enqueue(ShutdownApplication())).start()
 return original(self,on_started=ready)
AppRuntime.run_forever=run
entry=sys.argv.pop(1);sys.argv[0]=entry
runpy.run_path(entry,run_name="__main__")
'''.replace("REPORT", repr(str(report))), encoding="utf-8")
    keys = load_trusted_release_keyring(root / "launcher/managed-update-trusted-keys.json")
    verifier = Ed25519ManifestVerifier(ssh_keygen=root / "tools/ssh-keygen.exe",
        trusted_keys=keys.verification_keys(), work_root=out / "verification", environment=os.environ)
    layout = ManagedInstallLayout(install_root=root, shared_root=shared, manifest_verifier=verifier)
    layout.prove_current_install()
    processes = []

    def start(command, environment, cwd):
        command = list(command)
        command.insert(2, str(helper))
        process = start_detached_process(command, environment, cwd)
        processes.append(process)
        return process

    lifecycle = SubprocessManagedApplicationLifecycle(layout=layout, environment=os.environ,
        shutdown=lambda _: None, now=lambda: "2026-10-03T00:00:00Z", start_process=start)
    launch = lifecycle.launch(version_root=root / "versions" / owner["version"],
        transaction_id=transaction_id("probe-" + uuid.uuid4().hex),
        launch_attempt_id=launch_attempt_id("attempt-" + uuid.uuid4().hex), expected_version=owner["version"])
    try:
        lifecycle.await_health(launch, timeout_sec=20)
        for process in processes:
            assert process.wait(timeout=20) == 0
        result = json.loads(report.read_text())
        assert result["runtime_ready"] and not result["console_present"]
        result.update(identity_bound_health="passed", typed_shutdown="passed")
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        return 0
    finally:
        lifecycle.stop(launch, timeout_sec=3)


if __name__ == "__main__":
    raise SystemExit(main())
