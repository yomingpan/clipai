from pathlib import Path
import json
import subprocess
import sys
import venv

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


def _redirected_handle(tmp_path: Path, *, home_matches: bool = True, actual_matches: bool = True):
    expected = tmp_path / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"redirector")
    runtime = tmp_path / "runtime" / "python.exe"
    runtime.parent.mkdir()
    runtime.write_bytes(b"runtime")
    home = runtime.parent if home_matches else tmp_path / "foreign"
    (expected.parent.parent / "pyvenv.cfg").write_text(f"home = {home}\n", encoding="utf-8")
    closed = []
    handle = WindowsManagedProcessHandle(
        process_id=1234, expected_executable=expected, expected_runtime_executable=runtime,
        open_process=lambda _access, _pid: 88,
        query_image=lambda _handle: str(runtime if actual_matches else tmp_path / "foreign" / "python.exe"),
        wait_for_single_object=lambda _handle, _timeout: WAIT_OBJECT_0,
        close_handle=lambda value: closed.append(value),
    )
    return handle, closed


def test_version_venv_redirector_accepts_only_its_explicit_base_runtime(tmp_path: Path):
    handle, closed = _redirected_handle(tmp_path)
    handle.wait_for_exit(timeout_sec=1)
    handle.close()
    assert closed == [88]


@pytest.mark.parametrize("home_matches,actual_matches", [(False, True), (True, False)])
def test_redirector_rejects_foreign_venv_home_or_process_image(tmp_path: Path, home_matches, actual_matches):
    with pytest.raises(ManagedProcessIdentityError, match="does not match"):
        _redirected_handle(tmp_path, home_matches=home_matches, actual_matches=actual_matches)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="real Windows venv redirector")
def test_real_windows_venv_process_image_and_retained_shutdown(tmp_path: Path):
    env_root = tmp_path / ".venv"
    venv.EnvBuilder(with_pip=False).create(env_root)
    python = env_root / "Scripts" / "python.exe"
    script = "import json,os,sys; print(json.dumps([os.getpid(),sys.executable]),flush=True); sys.stdin.readline()"
    process = subprocess.Popen(
        [str(python), "-I", "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        process_id, logical_python = json.loads(process.stdout.readline())
        assert Path(logical_python).resolve() == python.resolve()
        with pytest.raises(ManagedProcessIdentityError, match="does not match"):
            WindowsManagedProcessHandle(process_id=process_id, expected_executable=python)
        with WindowsManagedProcessHandle(
            process_id=process_id, expected_executable=python,
            expected_runtime_executable=sys._base_executable,
        ) as handle:
            process.stdin.write("exit\n")
            process.stdin.flush()
            handle.wait_for_exit(timeout_sec=5)
        assert process.wait(timeout=5) == 0
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
