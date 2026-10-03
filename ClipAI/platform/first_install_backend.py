from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from ClipAI.core.first_install import InstallCancellation, InstallCancelled
from ClipAI.core.first_install import RetainedDataUninstallIntent
from ClipAI.core.managed_update_commands import InstallManagedCommand
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.installation_windows import WindowsInstallationIntegration, assert_installation_idle
from ClipAI.platform.managed_installer import FilesystemManagedInstaller
from ClipAI.platform.managed_update_fs import atomic_write_json, canonical_path, read_json, remove_tree, require_contained
from ClipAI.platform.managed_update_mutex import admit_installation
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier


OWNER_KIND = "clipai-first-install-owner-v1"
OWNED_DIRECTORIES = ("runtime", "tools", "setup-engine", "versions", "launcher")
OWNED_FILES = ("managed-install.json", "install-state.json")


@dataclass(frozen=True)
class BootstrapInputs:
    source: Path
    product: str
    registry_name: str


def read_owner(root: Path, shared: Path) -> dict:
    owner = read_json(root / "first-install-owner.json")
    if (owner.get("owner_kind") != OWNER_KIND or owner.get("schema_version") != 1
            or canonical_path(owner["install_root"]) != canonical_path(root)
            or canonical_path(owner["shared_root"]) != canonical_path(shared)
            or owner["owned_directories"] != list(OWNED_DIRECTORIES)
            or owner["owned_files"] != list(OWNED_FILES)):
        raise ValueError("installation ownership is not proven")
    for relative in (*OWNED_DIRECTORIES, *OWNED_FILES):
        path = root / relative
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError("owned path is redirected")
        require_contained(root, path)
    if root == shared or shared.is_relative_to(root) or root.is_relative_to(shared):
        raise ValueError("install and retained data roots overlap")
    return owner


class FilesystemFirstInstallBackend:
    def __init__(self, inputs: BootstrapInputs, environment: dict[str, str]) -> None:
        self._inputs, self._environment = inputs, environment

    def begin(self, command: InstallManagedCommand, cancellation: InstallCancellation):
        admission = admit_installation(command.install_root)
        try:
            root, shared = canonical_path(command.install_root), canonical_path(command.shared_root)
            if root == shared or shared.is_relative_to(root) or root.is_relative_to(shared):
                raise ValueError("install and retained data roots overlap")
            if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
                raise ValueError("installation root is redirected")
            if root.exists() and any(root.iterdir()):
                raise FileExistsError("existing_or_interrupted_installation_use_maintenance")
            transaction_root = shared / "managed-update/transactions" / str(command.transaction_id)
            owner = {"schema_version": 1, "owner_kind": OWNER_KIND,
                     "transaction_id": str(command.transaction_id), "managed_install_id": command.managed_install_id,
                     "install_root": str(root), "shared_root": str(shared),
                     "phase": "admitted", "product": self._inputs.product, "registry_name": self._inputs.registry_name,
                     "writer_process_id": os.getpid(), "writer_executable": str(Path(sys.executable).resolve()),
                     "version": command.expected_version, "owned_directories": list(OWNED_DIRECTORIES),
                     "owned_files": list(OWNED_FILES)}
            # Ownership precedes runtime/tool/payload writes; unknown crash gaps fail closed.
            atomic_write_json(transaction_root / "initial-install.json", owner)
            atomic_write_json(root / "first-install-owner.json", owner)
            return _InstallOperation(command, admission, self._inputs, self._environment,
                                     cancellation, owner, transaction_root)
        except Exception:
            admission.close()
            raise


class _InstallOperation:
    def __init__(self, command, admission, inputs, environment, cancellation, owner, transaction_root):
        self.command, self.admission, self.inputs = command, admission, inputs
        self.environment, self.cancellation = environment, cancellation
        self.owner, self.transaction_root = owner, transaction_root
        self.work = None
        self.children_settled = True
        self.started = time.monotonic()

    def _record(self, phase: str) -> None:
        self.admission.require_active(self.command.install_root)
        self.owner["phase"] = phase
        self.owner["operation_elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        atomic_write_json(self.transaction_root / "initial-install.json", self.owner)
        atomic_write_json(self.command.install_root / "first-install-owner.json", self.owner)

    def _run(self, arguments, environment, timeout):
        if self.cancellation.is_cancelled():
            raise InstallCancelled()
        started = time.monotonic()
        process = subprocess.Popen(list(arguments), env=dict(environment), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    # Caller inspects only the successful identity probe output.
                    if self.cancellation.is_cancelled():
                        raise InstallCancelled()
                    return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started > timeout:
                        self.children_settled = False
                        raise TimeoutError("offline_install_step_timeout")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)

    def prepare(self) -> None:
        self._record("copying_bootstrap")
        for name in ("runtime", "tools", "setup-engine"):
            if self.cancellation.is_cancelled():
                raise InstallCancelled()
            shutil.copytree(self.inputs.source / name, self.command.install_root / name)
        keyring_path = self.command.install_root / "setup-engine/managed-update-trusted-keys.json"
        keyring = load_trusted_release_keyring(keyring_path)
        verifier = Ed25519ManifestVerifier(
            ssh_keygen=self.command.install_root / "tools/ssh-keygen.exe",
            trusted_keys=keyring.verification_keys(), work_root=self.transaction_root / "verification",
            environment=self.environment,
        )
        self._record("preparing_payload")
        installer = FilesystemManagedInstaller(
            manifest_verifier=verifier, candidate_builder=OfflineCandidateEnvironmentBuilder(
                environment=self.environment, runner=self._run, timeout_sec=300),
            trusted_keyring_path=keyring_path,
        )
        self.work = installer.open_install(self.command, self.admission)
        self.work.prepare()

    def commit(self) -> None:
        self._record("commit_intent")
        if self.work is None:
            raise RuntimeError("installation is not prepared")
        self.work.commit()
        self._record("committed")

    def is_committed(self) -> bool:
        marker = self.command.install_root / "managed-install.json"
        if not marker.is_file():
            return False
        return read_json(marker).get("managed_install_id") == self.command.managed_install_id

    def integrate(self) -> None:
        self._record("integration_intent")
        integration = WindowsInstallationIntegration(
            product=self.inputs.product, registry_name=self.inputs.registry_name,
            root=self.command.install_root, shared=self.command.shared_root,
            install_id=self.command.managed_install_id, version=self.command.expected_version,
            work_root=self.transaction_root,
            environment=self.environment,
        )
        integration.create()
        self._record("installed")

    def cleanup(self) -> None:
        if not self.children_settled:
            raise RuntimeError("child_containment_pending_process_exit")
        if self.is_committed():
            raise RuntimeError("committed installation cannot be cancelled")
        owner = read_owner(self.command.install_root, self.command.shared_root)
        if (owner["transaction_id"] != str(self.command.transaction_id)
                or owner["managed_install_id"] != self.command.managed_install_id):
            raise RuntimeError("installation_ownership_changed")
        self._record("cleanup_intent")
        for relative in OWNED_DIRECTORIES:
            remove_tree(require_contained(self.command.install_root, self.command.install_root / relative))
        for relative in OWNED_FILES:
            (self.command.install_root / relative).unlink(missing_ok=True)
        atomic_write_json(self.transaction_root / "initial-install.json", {**self.owner, "phase": "cleaned"})
        (self.command.install_root / "first-install-owner.json").unlink()
        if not any(self.command.install_root.iterdir()):
            self.command.install_root.rmdir()

    def close(self) -> None:
        self.admission.close()


def uninstall_owned_installation(root: Path, shared: Path, *, environment: dict[str, str]) -> None:
    root, shared = canonical_path(root), canonical_path(shared)
    admission = admit_installation(root)
    try:
        owner = read_owner(root, shared)
        assert_installation_idle(root)
        marker = root / "managed-install.json"
        if marker.exists() and read_json(marker)["managed_install_id"] != owner["managed_install_id"]:
            raise ValueError("installed identity changed")
        work = shared / "managed-update/transactions" / owner["transaction_id"]
        integration = WindowsInstallationIntegration(
            product=owner["product"], registry_name=owner["registry_name"], root=root, shared=shared,
            install_id=owner["managed_install_id"], version=owner["version"], work_root=work,
            environment=environment,
        )
        integration.validate_removal()
        owner["phase"] = "uninstall_intent"
        atomic_write_json(work / "initial-install.json", owner)
        atomic_write_json(root / "first-install-owner.json", owner)
        # Keep native maintenance entry until owned files have settled.
        for name in OWNED_DIRECTORIES:
            remove_tree(require_contained(root, root / name))
        for name in OWNED_FILES:
            (root / name).unlink(missing_ok=True)
        integration.remove()
        atomic_write_json(work / "initial-install.json", {**owner, "phase": "uninstalled_data_retained"})
        (root / "first-install-owner.json").unlink()
        if not any(root.iterdir()):
            root.rmdir()
    finally:
        admission.close()


class FilesystemRetainedDataUninstaller:
    def __init__(self, environment: dict[str, str]) -> None:
        self.environment = environment

    def remove(self, intent: RetainedDataUninstallIntent) -> None:
        uninstall_owned_installation(intent.install_root, intent.shared_root, environment=self.environment)


def start_maintenance_helper(root: Path, shared: Path, *, temporary_root: Path,
                             environment: dict[str, str]) -> None:
    import uuid
    read_owner(root, shared)
    helper = temporary_root / f"clipai-maintenance-{uuid.uuid4().hex}"
    helper.mkdir(exist_ok=False)
    for name in ("runtime", "tools", "setup-engine"):
        shutil.copytree(root / name, helper / name)
    subprocess.Popen([str(helper / "runtime/pythonw.exe"), "-I",
                      str(helper / "setup-engine/entry.py"), "remove-worker",
                      "--install-root", str(root), "--shared-root", str(shared)],
                     env=dict(environment), creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
