from pathlib import Path

import pytest

from ClipAI.platform.managed_process import (
    PROCESS_QUERY_LIMITED_INFORMATION,
    SYNCHRONIZE,
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    ManagedProcessIdentityError,
    WindowsManagedProcessHandle,
)


def _handle(tmp_path: Path, *, actual: Path | None = None, wait_result: int = WAIT_OBJECT_0):
    expected = (tmp_path / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe").resolve()
    opened = []
    waited = []
    closed = []
    handle = WindowsManagedProcessHandle(
        process_id=1234,
        expected_executable=expected,
        open_process=lambda access, process_id: opened.append((access, process_id)) or 88,
        query_image=lambda _handle: str(actual or expected),
        wait_for_single_object=lambda value, timeout: waited.append((value, timeout)) or wait_result,
        close_handle=lambda value: closed.append(value),
    )
    return handle, opened, waited, closed


def test_process_handle_is_opened_immediately_with_exact_identity_and_waited(tmp_path: Path):
    handle, opened, waited, closed = _handle(tmp_path)
    assert opened == [(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, 1234)]
    handle.wait_for_exit(timeout_sec=20.0)
    assert waited == [(88, 20_000)]
    handle.close()
    handle.close()
    assert closed == [88]


def test_process_identity_rejects_same_basename_at_different_path_and_closes_handle(tmp_path: Path):
    expected = (tmp_path / "other" / "python.exe").resolve()
    closed = []
    with pytest.raises(ManagedProcessIdentityError, match="does not match"):
        WindowsManagedProcessHandle(
            process_id=1234,
            expected_executable=expected,
            open_process=lambda _access, _pid: 88,
            query_image=lambda _handle: str((tmp_path / "managed" / "python.exe").resolve()),
            wait_for_single_object=lambda _handle, _timeout: WAIT_OBJECT_0,
            close_handle=lambda value: closed.append(value),
        )
    assert closed == [88]


def test_process_wait_timeout_is_not_treated_as_shutdown(tmp_path: Path):
    handle, _, _, closed = _handle(tmp_path, wait_result=WAIT_TIMEOUT)
    with pytest.raises(TimeoutError, match="did not shut down"):
        handle.wait_for_exit(timeout_sec=0.25)
    handle.close()
    assert closed == [88]


def test_process_open_failure_is_explicit(tmp_path: Path):
    with pytest.raises(ManagedProcessIdentityError, match="open"):
        WindowsManagedProcessHandle(
            process_id=1234,
            expected_executable=tmp_path / "python.exe",
            open_process=lambda _access, _pid: 0,
            query_image=lambda _handle: "unused",
            wait_for_single_object=lambda _handle, _timeout: WAIT_OBJECT_0,
            close_handle=lambda _handle: None,
        )
