from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys

from ClipAI.platform.managed_process import _windows_process_functions
from ClipAI.core.first_install import InstallationBusyError
from ClipAI.platform.managed_update_fs import atomic_write_json, canonical_path


def current_user_desktop() -> Path:
    """Resolve the Windows Desktop known folder, including redirected desktops."""
    import uuid

    folder_id = (ctypes.c_ubyte * 16).from_buffer_copy(
        uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641").bytes_le)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                         ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole = ctypes.WinDLL("ole32")
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    result = ctypes.c_void_p()
    status = shell.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(result))
    try:
        if status != 0 or not result.value:
            raise OSError("desktop_folder_unavailable")
        return Path(ctypes.wstring_at(result.value))
    finally:
        if result.value:
            ole.CoTaskMemFree(result)


def install_process_containment() -> int:
    """Contain this bootstrap and all children until process exit, including crashes.

    Keep the non-inheritable handle alive until OS process teardown; closing it
    earlier would terminate this bootstrap too. Never use this for app launch.
    """
    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                    ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise OSError(ctypes.get_last_error(), "bootstrap child containment unavailable")
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise OSError(ctypes.get_last_error(), "bootstrap child containment unavailable")
    return int(handle)


def assert_installation_idle(root: Path) -> None:
    """Fail busy, without killing any app, for processes using this private runtime."""
    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
                    ("flags", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("process inventory unavailable")
    open_process, query_image, _wait, close = _windows_process_functions()
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            if entry.pid != os.getpid() and entry.exe.casefold() in {"python.exe", "pythonw.exe"}:
                handle = open_process(0x1000, entry.pid)
                if not handle:
                    # A race with exit is harmless; denied inspection is not proof of idle.
                    if ctypes.get_last_error() not in {87, 1168}:
                        raise OSError("unable to prove Python process ownership")
                else:
                    try:
                        if canonical_path(query_image(handle)).is_relative_to(canonical_path(root)):
                            raise InstallationBusyError("installation_busy_close_clipai_and_retry")
                    finally:
                        close(handle)
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)


class WindowsInstallationIntegration:
    """Own the exact per-user shortcut/registry receipts for one installation."""

    def __init__(self, *, product: str, registry_name: str, root: Path, shared: Path,
                 install_id: str, version: str, work_root: Path, environment: dict[str, str]) -> None:
        if not product or any(char in product for char in '/\\:'):
            raise ValueError("product name is invalid")
        if not registry_name or any(char in registry_name for char in '/\\:'):
            raise ValueError("registry identity is invalid")
        self.product, self.root, self.shared = product, canonical_path(root), canonical_path(shared)
        self.install_id, self.version, self.work_root = install_id, version, work_root
        self.environment = environment
        self.registry = f"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{registry_name}"
        self.group = Path(environment["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs" / product
        self.icon = self.root / "setup-engine/clipai.ico"

    def _desktop_receipt(self) -> Path | None:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry) as key:
                value = winreg.QueryValueEx(key, "ManagedDesktopShortcut")[0]
        except FileNotFoundError:
            # Older installations did not create a desktop shortcut.
            return None
        expected = current_user_desktop() / f"{self.product}.lnk"
        if canonical_path(value) != canonical_path(expected):
            raise RuntimeError("desktop_shortcut_identity_changed")
        return expected

    def _arguments(self, action: str) -> list[str]:
        return ["-I", str(self.root / "setup-engine/entry.py"), action,
                "--install-root", str(self.root), "--shared-root", str(self.shared)]

    def _shortcut(self, path: Path, action: str, *, create: bool) -> None:
        request = self.work_root / "shortcut-intent.json"
        atomic_write_json(request, {"path": str(path), "target": str(self.root / "runtime/pythonw.exe"),
                                    "arguments": subprocess.list2cmdline(self._arguments(action)),
                                    "icon": str(self.icon), "create": create})
        try:
            worker = Path(__file__).with_name('windows_shell_link.py')
            result = subprocess.run([sys.executable, '-I', str(worker), str(request)],
                                    env=self.environment,
                                    capture_output=True, timeout=30, check=False,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError("shortcut_integration_failed")
        finally:
            request.unlink(missing_ok=True)

    def create(self) -> None:
        import winreg
        if self.group.exists():
            raise FileExistsError("start_menu_group_already_exists")
        desktop = current_user_desktop() / f"{self.product}.lnk"
        if desktop.exists():
            raise FileExistsError("desktop_shortcut_already_exists")
        if not self.icon.is_file():
            raise FileNotFoundError("installation_icon_missing")
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry):
                raise FileExistsError("uninstall_registration_already_exists")
        except FileNotFoundError:
            pass
        self.group.mkdir(parents=True)
        self._shortcut(self.group / f"{self.product}.lnk", "launch", create=True)
        self._shortcut(self.group / "Uninstall.lnk", "uninstall", create=True)
        uninstall = subprocess.list2cmdline([str(self.root / "runtime/pythonw.exe"), *self._arguments("uninstall")])
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.registry) as key:
            for name, value in {"DisplayName": self.product, "DisplayVersion": self.version,
                                "Publisher": "ClipAI local acceptance candidate",
                                "InstallLocation": str(self.root), "UninstallString": uninstall,
                                "DisplayIcon": str(self.icon),
                                "ManagedDesktopShortcut": str(desktop),
                                "ManagedInstallId": self.install_id}.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            for name in ("NoModify", "NoRepair"):
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        self._shortcut(desktop, "launch", create=True)

    def validate_removal(self) -> None:
        """Prove native receipt ownership before deleting any program files."""
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry) as key:
                if (winreg.QueryValueEx(key, "InstallLocation")[0] != str(self.root)
                        or winreg.QueryValueEx(key, "ManagedInstallId")[0] != self.install_id):
                    raise RuntimeError("uninstall_registration_identity_changed")
        except FileNotFoundError:
            pass
        for name, action in ((f"{self.product}.lnk", "launch"), ("Uninstall.lnk", "uninstall")):
            path = self.group / name
            if path.exists():
                self._shortcut(path, action, create=False)
        desktop = self._desktop_receipt()
        if desktop is not None and desktop.exists():
            self._shortcut(desktop, "launch", create=False)

    def remove(self) -> None:
        import winreg
        self.validate_removal()
        desktop = self._desktop_receipt()
        if desktop is not None and desktop.exists():
            desktop.unlink()
        for name in (f"{self.product}.lnk", "Uninstall.lnk"):
            path = self.group / name
            if path.exists():
                path.unlink()
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.registry)
        except FileNotFoundError:
            pass
        if self.group.exists() and not any(self.group.iterdir()):
            self.group.rmdir()
