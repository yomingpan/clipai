import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from ClipAI.platform.first_install_backend import _MAINTENANCE_SUPERVISOR
from ClipAI.platform import first_install_backend as backend
from ClipAI.platform.managed_update_fs import atomic_write_json
from ClipAI.core.first_install import UninstallPhase, UninstallSnapshot


@pytest.mark.integration
@pytest.mark.skipif(os.name != "nt", reason="Windows helper supervisor")
@pytest.mark.parametrize("phase,error,exit_code,blocked,expected", [
    ("failed", "InstallationBusyError", 1, False, "ClipAI is still running"),
    ("failed", "OSError", 1, False, "Error: OSError"),
    ("uninstalled", None, 0, False, "Settings and data have been retained"),
    ("uninstalled", None, 1, False, "Removal did not complete"),
    ("failed", "InstallationBusyError", 0, False, "Removal did not complete"),
    ("failed", "sensitive raw text\ncredential", 1, False, "Removal did not complete"),
    ("unknown", None, 0, False, "Removal did not complete"),
    ("missing", None, 0, False, "Removal did not complete"),
    ("malformed", None, 0, False, "Removal did not complete"),
    ("oversize", None, 0, False, "Removal did not complete"),
    ("failed", ["InstallationBusyError"], 1, False, "Removal did not complete"),
    ("uninstalled", None, 0, True, "Temporary helper cleanup did not complete"),
    ("failed", "InstallationBusyError", 1, True, "Temporary helper cleanup did not complete"),
])
def test_native_supervisor_preserves_terminal_reason_and_rejects_false_success(tmp_path, phase, error, exit_code, blocked, expected):
    helper = tmp_path / ("clipai-maintenance-" + uuid.uuid4().hex)
    (helper / "runtime").mkdir(parents=True)
    shutil.copyfile(Path(os.environ["SYSTEMROOT"]) / "System32/cmd.exe", helper / "runtime/python.exe")
    atomic_write_json(helper / "maintenance-request.json", {
        "helper_root": str(helper), "temporary_root": str(tmp_path), "product": "Fixture",
        "delete_user_data": False,
        "arguments": f'/d /c ""{helper / "worker.cmd"}""',
    })
    payload = json.dumps({"schema_version": 1, "phase": phase, "error_code": error})
    if phase == "malformed":
        payload = "{"
    elif phase == "oversize":
        payload = "a" * 1025
    write = '> "%~dp0maintenance-result.json" echo ' + payload + '\n' if phase != "missing" else ""
    (helper / "worker.cmd").write_text(
        '@echo off\n' + write + f'exit /b {exit_code}\n',
        encoding="ascii",
    )
    # Replace only the attended UI with a capture. Process, output transport,
    # settlement, cleanup and the actual terminal message branch stay real.
    capture = '''Add-Type @'
namespace Windows.Forms {
    public static class MessageBox {
        public static int Show(string message, string product, string buttons, string icon) {
            System.Console.WriteLine(message);
            return 0;
        }
    }
}
'@
'''
    script = capture + "$taskRoot = '" + str(helper).replace("'", "''") + "'\n"
    script += _MAINTENANCE_SUPERVISOR.replace("Add-Type -AssemblyName System.Windows.Forms", "")
    lock = (helper / "held.txt").open("w") if blocked else None
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                                 base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
                                capture_output=True, text=True, timeout=30)
    finally:
        if lock is not None:
            lock.close()
    assert result.returncode == 0, result.stderr
    assert helper.exists() is blocked
    assert expected in result.stdout
    assert ("cleanup did not complete" in result.stdout) is blocked
    assert "sensitive" not in result.stdout
    if phase != "uninstalled" or exit_code != 0 or blocked:
        assert "have been retained" not in result.stdout


@pytest.mark.parametrize("delete_data", [False, True])
def test_helper_launch_transfers_policy_and_cleans_up_failed_start(tmp_path, monkeypatch, delete_data):
    root, shared, temporary = tmp_path / "program", tmp_path / "data", tmp_path / "temporary"
    temporary.mkdir()
    for name in ("runtime", "tools", "setup-engine"):
        (root / name).mkdir(parents=True)
        (root / name / "owned.txt").write_text("fixture")
    monkeypatch.setattr(backend, "read_owner", lambda *_: {"product": "Fixture"})
    def reject_launch(command, **kwargs):
        helpers = list(temporary.glob("clipai-maintenance-*"))
        assert len(helpers) == 1
        request = json.loads((helpers[0] / "maintenance-request.json").read_text())
        assert request["delete_user_data"] is delete_data
        assert ("--delete-user-data" in request["arguments"]) is delete_data
        assert "--quiet" in request["arguments"]
        assert "--maintenance-result" in request["arguments"]
        assert kwargs["cwd"] == temporary.resolve()
        script = base64.b64decode(command[-1]).decode("utf-16-le")
        assert "-WindowStyle Hidden" in script
        raise OSError("fixture process launch failed")
    monkeypatch.setattr(backend.subprocess, "Popen", reject_launch)
    with pytest.raises(OSError):
        backend.start_maintenance_helper(root, shared, temporary_root=temporary,
                                         environment={"SYSTEMROOT": str(tmp_path)}, delete_user_data=delete_data)
    assert not list(temporary.iterdir())
    assert (root / "runtime/owned.txt").read_text() == "fixture"


@pytest.mark.integration
@pytest.mark.skipif(os.name != "nt", reason="Windows helper supervisor")
@pytest.mark.parametrize("exit_code", [0, 1])
def test_native_supervisor_waits_for_worker_and_removes_its_exact_helper(tmp_path, exit_code):
    tmp_path = tmp_path / "測試 空間's"
    tmp_path.mkdir()
    helper = tmp_path / ("clipai-maintenance-" + uuid.uuid4().hex)
    (helper / "runtime").mkdir(parents=True)
    shutil.copyfile(Path(os.environ["SYSTEMROOT"]) / "System32/cmd.exe", helper / "runtime/python.exe")
    atomic_write_json(helper / "maintenance-request.json", {
        "helper_root": str(helper), "temporary_root": str(tmp_path), "product": "Fixture",
        "delete_user_data": True, "arguments": f"/c exit {exit_code}",
    })
    backend.write_maintenance_result(helper, UninstallSnapshot("fixture",
        UninstallPhase.REMOVED if exit_code == 0 else UninstallPhase.FAILED,
        None if exit_code == 0 else "OSError"))
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("keep")
    # Use the actual process/wait/cleanup boundary; suppress only the attended
    # terminal message box so this probe runs without user interaction.
    script = "$taskRoot = '" + str(helper).replace("'", "''") + "'\n"
    script += _MAINTENANCE_SUPERVISOR.split("Add-Type -AssemblyName System.Windows.Forms")[0]
    script += "@{succeeded=$succeeded; settled=$settled} | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                             base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"succeeded": exit_code == 0, "settled": True}
    assert not helper.exists()
    assert unrelated.read_text() == "keep"


def test_helper_result_is_terminal_and_bounded(tmp_path):
    with pytest.raises(ValueError, match="terminal"):
        backend.write_maintenance_result(tmp_path, UninstallSnapshot("fixture", UninstallPhase.REMOVING))
    assert not (tmp_path / "maintenance-result.json").exists()
    backend.write_maintenance_result(tmp_path, UninstallSnapshot("fixture", UninstallPhase.FAILED, "private text " * 500))
    result = tmp_path / "maintenance-result.json"
    assert result.stat().st_size <= 1024
    assert json.loads(result.read_text())["error_code"] == "UnknownRemovalError"
