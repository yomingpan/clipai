"""Attended About acceptance launcher, using the installed wheel and real runtime.

Run with the owned Candidate version venv's Python -I. No automatic update or
provider request; the operator must click About Update. Not clean-VM evidence.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlparse
import uuid


def require_isolated_url(url: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.hostname.lower() in {"github.com", "api.github.com", "raw.githubusercontent.com"}
            or parsed.fragment):
        raise ValueError("an isolated, credential-free HTTPS catalog is required")
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--catalog-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    catalog_url = require_isolated_url(args.catalog_url)
    if not 30 <= args.timeout_seconds <= 600:
        parser.error("attended launch timeout must be 30–600 seconds")
    # Import only after argument validation, from this installed interpreter.
    import ClipAI
    import main as application
    from ClipAI.app.managed_update_composition import ManagedUpdateRuntimeConfiguration
    from ClipAI.app.managed_update_launch import ManagedLaunchExecutor
    from ClipAI.app.application_paths import build_managed_application_paths
    from ClipAI.core.commands import ShutdownApplication
    from ClipAI.core.managed_update import transaction_id, launch_attempt_id
    from ClipAI.core.managed_update_commands import LaunchManagedCommand
    from ClipAI.platform.first_install_backend import read_owner
    from ClipAI.platform.managed_install import ManagedInstallLayout
    from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
    from ClipAI.platform.update_signature import Ed25519ManifestVerifier
    if not Path(ClipAI.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError("launcher must run from the installed wheel")
    root, shared = args.install_root.resolve(), args.shared_root.resolve()
    owner = read_owner(root, shared)
    if owner["product"] != "ClipAI Candidate" or owner["registry_name"] != "ClipAI.LocalAcceptance.Candidate":
        raise ValueError("only the explicitly owned Candidate installation is accepted")
    # Keys remain the installation's admitted keys, never fetched from catalog.
    environment = {k: v for k, v in os.environ.items() if k.upper() in {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"}}
    environment["PATH"] = ""
    keys = load_trusted_release_keyring(root / "launcher/managed-update-trusted-keys.json")
    proof = ManagedInstallLayout(install_root=root, shared_root=shared, manifest_verifier=Ed25519ManifestVerifier(
        ssh_keygen=root / "tools/ssh-keygen.exe", trusted_keys=keys.verification_keys(),
        work_root=shared / "managed-update/about-acceptance", environment=environment,
    )).prove_update_client(executable_path=Path(sys.executable), process_id=os.getpid())
    relative_entry = proof.current.entrypoint.relative_to(proof.current.root)
    configuration = ManagedUpdateRuntimeConfiguration(
        proof.identity, root / "launcher/.venv/Scripts/python.exe", root / "launcher" / relative_entry,
        root / "runtime/python.exe", environment, catalog_url,
    )
    paths = build_managed_application_paths(proof.current.entrypoint.parent, shared, instance_name="default")
    original = application.build_runtime
    runtime = None
    timer = None
    def compose(*arguments, **keywords):
        nonlocal runtime
        runtime = original(*arguments, **keywords)
        return runtime
    application.build_runtime = compose
    def run_application(report_started):
        def started():
            nonlocal timer
            report_started()
            timer = threading.Timer(args.timeout_seconds, lambda: runtime.enqueue(ShutdownApplication()))
            timer.daemon = True
            timer.start()
            print("ISOLATED_ABOUT_READY: click About Update explicitly", flush=True)
        application._run_application(paths, managed_update=configuration, on_started=started)
    command = LaunchManagedCommand(shared, root, transaction_id("about-" + uuid.uuid4().hex),
                                   launch_attempt_id("about-" + uuid.uuid4().hex), proof.current.version)
    try:
        return ManagedLaunchExecutor(actual_version=importlib.metadata.version("clipai"),
            executable_path=Path(sys.executable), now=lambda: datetime.now(timezone.utc).isoformat(),
            run_application=run_application).execute(command)
    finally:
        application.build_runtime = original
        if timer:
            timer.cancel()


if __name__ == "__main__":
    raise SystemExit(main())
