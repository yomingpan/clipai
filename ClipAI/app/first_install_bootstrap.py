from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

from ClipAI.core.first_install import FirstInstallSnapshot, InstallPhase
from ClipAI.core.first_install import UninstallIntent, UninstallPhase, UninstallSnapshot
from ClipAI.core.managed_update import transaction_id
from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.platform.first_install_backend import (
    BootstrapInputs, FilesystemFirstInstallBackend, FilesystemUninstaller,
    read_owner, start_maintenance_helper, write_maintenance_result,
)
from ClipAI.platform.installation_windows import install_process_containment
from ClipAI.services.first_install import FirstInstallCoordinator, UninstallCoordinator


class _CancellationFile:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def is_cancelled(self) -> bool:
        return self.path is not None and self.path.exists()


def _publish(snapshot: FirstInstallSnapshot | UninstallSnapshot) -> None:
    print(f"CLIPAI_PHASE:{snapshot.phase.value}:{snapshot.error_code or ''}", flush=True)


def main(argv: list[str] | None = None, *, bootstrap_root: Path | None = None,
         environment: dict[str, str]) -> int:
    parser = argparse.ArgumentParser(description="ClipAI installation composition; no desktop runtime imports")
    parser.add_argument("action", choices=("install", "launch", "uninstall", "remove-worker", "selfcheck"))
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--shared-root", required=True, type=Path)
    parser.add_argument("--cancel-intent", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--delete-user-data", action="store_true")
    parser.add_argument("--maintenance-result", action="store_true")
    args = parser.parse_args(argv)
    if args.delete_user_data and args.action not in {"uninstall", "remove-worker"}:
        parser.error("--delete-user-data requires a removal action")
    if args.maintenance_result and args.action != "remove-worker":
        parser.error("--maintenance-result requires remove-worker")
    # Preserve the supplied spelling until the backend rejects redirected
    # removal paths; resolving here would erase symlink/junction evidence.
    root, shared = args.install_root.absolute(), args.shared_root.absolute()
    source = (bootstrap_root or Path(__file__).resolve().parents[3]).resolve()
    metadata = json.loads((source / "setup-engine/candidate.json").read_text(encoding="utf-8"))
    try:
        if args.action == "launch":
            # A stable entry delegates current-version proof and health to the
            # existing managed launcher. No speech/provider/output side effects.
            read_owner(root, shared)
            subprocess.Popen([str(root / "launcher/.venv/Scripts/python.exe"), "-I",
                              str(root / "launcher/payload/main.py")],
                             env=dict(environment), cwd=root,
                             creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            return 0
        if args.action == "uninstall":
            from ClipAI.ui.installation_maintenance import choose_uninstall
            if not args.quiet:
                choice = choose_uninstall(metadata["product"])
                if choice is None:
                    return 0
                args.delete_user_data = choice
            read_owner(root, shared)
            # Copy the trusted maintenance engine/runtime before self-removal.
            # A new Setup can also run remove-worker when the installed venv or
            # runtime is broken. Never depend on a version venv for maintenance.
            start_maintenance_helper(root, shared, temporary_root=Path(tempfile.gettempdir()), environment=environment,
                                     delete_user_data=args.delete_user_data)
            return 0
        if args.action == "remove-worker":
            # Parent Control Panel launcher must finish before the idle check.
            import time
            time.sleep(1)
            result = UninstallCoordinator(FilesystemUninstaller(environment)).execute(
                UninstallIntent(f"uninstall-{uuid.uuid4().hex}", root, shared, args.delete_user_data), publish=_publish)
            if args.maintenance_result:
                write_maintenance_result(source, result)
            if not args.quiet:
                from ClipAI.ui.installation_maintenance import show_maintenance_result
                show_maintenance_result(metadata["product"], success=result.phase == UninstallPhase.REMOVED,
                                        error_code=result.error_code or "", delete_user_data=args.delete_user_data)
            return 0 if result.phase == UninstallPhase.REMOVED else 1
        if args.action == "selfcheck":
            from ClipAI.platform.managed_install import ManagedInstallLayout
            from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
            from ClipAI.platform.update_signature import Ed25519ManifestVerifier
            read_owner(root, shared)
            keys = load_trusted_release_keyring(root / "setup-engine/managed-update-trusted-keys.json")
            ManagedInstallLayout(install_root=root, shared_root=shared, manifest_verifier=Ed25519ManifestVerifier(
                ssh_keygen=root / "tools/ssh-keygen.exe", trusted_keys=keys.verification_keys(),
                work_root=shared / "managed-update/selfcheck", environment=dict(environment),
            )).prove_current_install()
            print("CLIPAI_PHASE:selfcheck_passed:", flush=True)
            return 0
        # Keep the native job handle alive until process exit. All pip/venv
        # children die if the bootstrap is interrupted; normal app launch is
        # deliberately outside this job.
        containment_handle = install_process_containment()
        if not containment_handle:
            raise RuntimeError("bootstrap_containment_unavailable")
        release = metadata["release"]
        command = InstallManagedCommand(
            shared_root=shared, install_root=root, transaction_id=transaction_id(f"install-{uuid.uuid4().hex}"),
            expected_version=metadata["version"], bundle_path=source / "bundle.zip",
            bundle_size=release["bundle_size"], bundle_sha256=release["bundle_sha256"],
            manifest_sha256=release["manifest_sha256"], key_id=metadata["key_id"],
            managed_install_id=f"install-{uuid.uuid4().hex}", launcher_version=metadata["version"],
            base_python=root / "runtime/python.exe",
        )
        # Keep credentials/user Python/PIP settings out of installer subprocesses.
        environment = {key: value for key, value in environment.items()
                       if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"}}
        environment.update(PATH="", PYTHONDONTWRITEBYTECODE="1", PIP_NO_INDEX="1")
        coordinator = FirstInstallCoordinator(FilesystemFirstInstallBackend(
            BootstrapInputs(source, metadata["product"], metadata["registry_name"]), environment))
        result = coordinator.execute(command, cancellation=_CancellationFile(args.cancel_intent), publish=_publish)
        return 0 if result.phase == InstallPhase.INSTALLED else 1
    except Exception as exc:
        print(f"CLIPAI_PHASE:failed:{type(exc).__name__}", flush=True)
        if args.action == "launch" and not args.quiet:
            from ClipAI.ui.startup_error import show_startup_error
            show_startup_error("ClipAI Preview 無法啟動。請用同一個 Setup 移除後重裝；設定與資料會保留。\n\n" + type(exc).__name__)
        elif args.action in {"remove-worker", "uninstall"} and not args.quiet:
            from ClipAI.ui.installation_maintenance import show_maintenance_result
            show_maintenance_result(metadata["product"], success=False, error_code=type(exc).__name__)
        return 1
