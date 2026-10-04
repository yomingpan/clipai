from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from ClipAI.core.first_install import InstallCancellation, InstallCancelled
from ClipAI.core.first_install import UninstallIntent
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


def _require_unredirected_tree(path: Path) -> None:
    # lstat catches Windows junctions on Python 3.10 too. Never follow a
    # redirected parent or descendant while proving recursive-delete scope.
    def check(candidate: Path) -> None:
        if candidate.is_symlink() or (candidate.exists() and
                getattr(candidate.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("removal path is redirected")
    for parent in (path, *path.parents):
        check(parent)
    if path.exists():
        for parent, directories, files in os.walk(path, followlinks=False):
            for name in (*directories, *files):
                check(Path(parent) / name)


def _validate_data_removal(root: Path, shared: Path, owner: dict, environment: dict[str, str]) -> None:
    product = owner["product"]
    identities = {"ClipAI": "ClipAI.Desktop", "ClipAI Preview": "ClipAI.LocalAcceptance.Preview",
                  "ClipAI Candidate": "ClipAI.LocalAcceptance.Candidate"}
    if product not in identities or owner["registry_name"] != identities[product]:
        raise ValueError("unknown full-removal identity")
    app_data = canonical_path(environment["LOCALAPPDATA"])
    if (root != app_data / "Programs" / product or shared != app_data / product):
        raise ValueError("full removal requires the dedicated per-user roots")
    _require_unredirected_tree(root)
    _require_unredirected_tree(shared)
    if any(child.name not in (*OWNED_DIRECTORIES, *OWNED_FILES, "first-install-owner.json")
           for child in root.iterdir()):
        raise ValueError("unknown program files prevent complete removal")
    # Reinstalls can share data, but a different installation root cannot.
    for receipt in shared.glob("managed-update/transactions/*/initial-install.json"):
        previous = read_json(receipt)
        if (canonical_path(previous["install_root"]) != root
                or canonical_path(previous["shared_root"]) != shared
                or previous["product"] != product or previous["registry_name"] != owner["registry_name"]):
            raise ValueError("shared data belongs to another installation")


def uninstall_owned_installation(root: Path, shared: Path, *, environment: dict[str, str],
                                 delete_user_data: bool = False) -> None:
    if delete_user_data:
        _require_unredirected_tree(root)
        _require_unredirected_tree(shared)
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
        if delete_user_data:
            _validate_data_removal(root, shared, owner, environment)
        owner["phase"] = "uninstall_intent"
        atomic_write_json(work / "initial-install.json", owner)
        atomic_write_json(root / "first-install-owner.json", owner)
        # Keep native maintenance entry until owned files have settled.
        for name in OWNED_DIRECTORIES:
            remove_tree(require_contained(root, root / name))
        for name in OWNED_FILES:
            (root / name).unlink(missing_ok=True)
        # Native validation can write its shortcut request under shared, so
        # settle integration before removing data. Keep owner proof for retry.
        integration.remove()
        if delete_user_data:
            remove_tree(shared)
        if not delete_user_data:
            atomic_write_json(work / "initial-install.json", {**owner, "phase": "uninstalled_data_retained"})
        (root / "first-install-owner.json").unlink()
        if not any(root.iterdir()):
            root.rmdir()
    finally:
        admission.close()


class FilesystemUninstaller:
    def __init__(self, environment: dict[str, str]) -> None:
        self.environment = environment

    def remove(self, intent: UninstallIntent) -> None:
        uninstall_owned_installation(intent.install_root, intent.shared_root, environment=self.environment,
                                     delete_user_data=intent.delete_user_data)


def start_maintenance_helper(root: Path, shared: Path, *, temporary_root: Path,
                             environment: dict[str, str], delete_user_data: bool = False) -> None:
    import uuid
    read_owner(root, shared)
    _require_unredirected_tree(root)
    helper = temporary_root / f"clipai-maintenance-{uuid.uuid4().hex}"
    temporary_root = temporary_root.resolve()
    helper = require_contained(temporary_root, helper)
    helper.mkdir(exist_ok=False)
    try:
        _require_unredirected_tree(helper)
        for name in ("runtime", "tools", "setup-engine"):
            shutil.copytree(root / name, helper / name)
        command = ["-I", str(helper / "setup-engine/entry.py"), "remove-worker", "--quiet",
                   "--install-root", str(root), "--shared-root", str(shared)]
        if delete_user_data:
            command.append("--delete-user-data")
        atomic_write_json(helper / "maintenance-request.json", {
            "helper_root": str(helper), "temporary_root": str(temporary_root),
            "product": read_owner(root, shared)["product"], "delete_user_data": delete_user_data,
            "arguments": subprocess.list2cmdline(command),
        })
        import base64
        script = "$taskRoot = '" + str(helper).replace("'", "''") + "'\n" + _MAINTENANCE_SUPERVISOR
        executable = Path(environment["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.Popen([str(executable), "-NoProfile", "-NonInteractive", "-EncodedCommand",
                          base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
                         env=dict(environment), cwd=temporary_root,
                         creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    except Exception:
        remove_tree(require_contained(temporary_root, helper))
        raise


_MAINTENANCE_SUPERVISOR = r"""
$ErrorActionPreference = 'Stop'
$succeeded = $false
$settled = $false
$worker = $null
$request = Get-Content -LiteralPath (Join-Path $taskRoot 'maintenance-request.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$resolved = [IO.Path]::GetFullPath($taskRoot)
if ($resolved -ne $request.helper_root -or
    [IO.Path]::GetDirectoryName($resolved) -ne $request.temporary_root -or
    [IO.Path]::GetFileName($resolved) -notmatch '^clipai-maintenance-[0-9a-f]{32}$') { exit 1 }
try {
    $worker = Start-Process -FilePath (Join-Path $taskRoot 'runtime/python.exe') -ArgumentList $request.arguments -WorkingDirectory $request.temporary_root -WindowStyle Hidden -PassThru
    if (-not $worker.WaitForExit(600000)) { throw 'Removal did not settle within 10 minutes.' }
    $settled = $true
    $succeeded = $worker.ExitCode -eq 0
} catch { $succeeded = $false }
try {
    if ($settled -or $null -eq $worker) {
        function AssertPlainTree([string] $path) {
            $item = Get-Item -LiteralPath $path -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected helper.' }
            if ($item.PSIsContainer) {
                foreach ($child in Get-ChildItem -LiteralPath $path -Force) { AssertPlainTree $child.FullName }
            }
        }
        AssertPlainTree $resolved
        Remove-Item -LiteralPath $resolved -Recurse -Force
    } else { $succeeded = $false }
} catch { $succeeded = $false }
Add-Type -AssemblyName System.Windows.Forms
if ($succeeded) {
    $message = if ($request.delete_user_data) { 'Program files, settings, API keys and ClipAI data have been removed.' } else { 'Program files removed. Settings and data have been retained.' }
    [Windows.Forms.MessageBox]::Show($message, $request.product, 'OK', 'Information') | Out-Null
} else {
    [Windows.Forms.MessageBox]::Show('Removal or temporary helper cleanup did not complete. Exit ClipAI, then retry removal using the same Setup.', $request.product, 'OK', 'Error') | Out-Null
}
"""
