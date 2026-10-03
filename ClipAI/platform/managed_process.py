from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from ClipAI.platform.managed_update_fs import canonical_path


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF


class ManagedProcessIdentityError(OSError):
    pass


class WindowsManagedProcessHandle:
    """Retain and verify the exact old app process before update preparation."""

    def __init__(
        self,
        *,
        process_id: int,
        expected_executable: str | Path,
        open_process: Callable[[int, int], int] | None = None,
        query_image: Callable[[int], str] | None = None,
        wait_for_single_object: Callable[[int, int], int] | None = None,
        close_handle: Callable[[int], object] | None = None,
    ) -> None:
        if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
            raise ValueError("managed process id must be positive")
        functions = (open_process, query_image, wait_for_single_object, close_handle)
        if any(item is None for item in functions) and not all(item is None for item in functions):
            raise ValueError("managed process functions must be provided together")
        if all(item is None for item in functions):
            open_process, query_image, wait_for_single_object, close_handle = _windows_process_functions()
        assert open_process is not None
        assert query_image is not None
        assert wait_for_single_object is not None
        assert close_handle is not None
        self._wait_for_single_object = wait_for_single_object
        self._close_handle = close_handle
        self._lock = threading.Lock()
        access = SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
        handle = int(open_process(access, process_id) or 0)
        if not handle:
            raise ManagedProcessIdentityError("unable to open installed application process")
        self._handle = handle
        try:
            actual = canonical_path(query_image(handle))
            expected = canonical_path(expected_executable)
            if actual != expected:
                raise ManagedProcessIdentityError("installed process executable does not match request")
        except Exception:
            self.close()
            raise

    def wait_for_exit(self, *, timeout_sec: float) -> None:
        if timeout_sec <= 0:
            raise ValueError("process wait timeout must be positive")
        with self._lock:
            handle = self._handle
        if not handle:
            raise ManagedProcessIdentityError("installed process handle is closed")
        milliseconds = min(0xFFFFFFFE, max(1, int(timeout_sec * 1000)))
        result = int(self._wait_for_single_object(handle, milliseconds))
        if result == WAIT_TIMEOUT:
            raise TimeoutError("installed application did not shut down")
        if result != WAIT_OBJECT_0:
            raise ManagedProcessIdentityError("unable to wait for installed application process")

    def close(self) -> None:
        with self._lock:
            handle, self._handle = self._handle, 0
        if handle:
            self._close_handle(handle)

    def __enter__(self) -> WindowsManagedProcessHandle:
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

def _windows_process_functions():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    query_image = kernel32.QueryFullProcessImageNameW
    query_image.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    query_image.restype = wintypes.BOOL
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    def open_adapter(access: int, process_id: int) -> int:
        return int(open_process(access, False, process_id) or 0)

    def query_adapter(handle: int) -> str:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not query_image(handle, 0, buffer, ctypes.byref(size)):
            raise ManagedProcessIdentityError("unable to query installed process executable")
        return buffer.value

    return open_adapter, query_adapter, wait, close
