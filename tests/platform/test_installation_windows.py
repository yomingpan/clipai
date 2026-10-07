from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from ClipAI.platform import installation_windows as windows


def integration(tmp_path, monkeypatch):
    registry = {}
    def open_key(_hive, name):
        if name not in registry:
            raise FileNotFoundError(name)
        return nullcontext(registry[name])
    def query(key, name):
        if name not in key:
            raise FileNotFoundError(name)
        return key[name], 1
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER=0, REG_SZ=1, REG_DWORD=4, OpenKey=open_key,
        CreateKey=lambda _, name: nullcontext(registry.setdefault(name, {})),
        QueryValueEx=query, SetValueEx=lambda key, name, _reserved, _kind, value: key.update({name: value}),
        DeleteKey=lambda _, name: registry.pop(name)))
    desktop = tmp_path / "redirected-desktop"
    desktop.mkdir()
    monkeypatch.setattr(windows, "current_user_desktop", lambda: desktop)
    root = tmp_path / "program"
    (root / "setup-engine").mkdir(parents=True)
    (root / "setup-engine/clipai.ico").write_bytes(b"icon")
    result = windows.WindowsInstallationIntegration(
        product="ClipAI Preview", registry_name="Preview.Test", root=root, shared=tmp_path / "data",
        install_id="test-install", version="3.7.8", work_root=tmp_path,
        environment={"APPDATA": str(tmp_path / "roaming")})
    links = {}
    def shortcuts(batch, *, create):
        for path, action in batch:
            if create:
                links[path] = action
                path.touch()
            elif links[path] != action:
                raise RuntimeError("Shortcut ownership changed")
    monkeypatch.setattr(result, "_shortcuts", shortcuts)
    return result, registry, desktop, links


def test_install_creates_desktop_receipt_and_uninstall_removes_only_owned_link(tmp_path, monkeypatch):
    native, registry, desktop, links = integration(tmp_path, monkeypatch)
    native.create()
    path = desktop / "ClipAI Preview.lnk"
    assert links[path] == "launch"
    assert registry[native.registry]["DisplayIcon"] == str(native.icon)
    unrelated = desktop / "Other.lnk"
    unrelated.touch()
    native.remove()
    assert not path.exists()
    assert unrelated.exists()


def test_install_preserves_existing_desktop_shortcut(tmp_path, monkeypatch):
    native, registry, desktop, _ = integration(tmp_path, monkeypatch)
    path = desktop / "ClipAI Preview.lnk"
    path.write_text("user shortcut")
    with pytest.raises(FileExistsError, match="desktop_shortcut_already_exists"):
        native.create()
    assert path.read_text() == "user shortcut"
    assert registry == {}


def test_changed_desktop_target_blocks_removal(tmp_path, monkeypatch):
    native, registry, desktop, links = integration(tmp_path, monkeypatch)
    native.create()
    path = desktop / "ClipAI Preview.lnk"
    links[path] = "user-modified-target"
    with pytest.raises(RuntimeError, match="ownership changed"):
        native.remove()
    assert path.exists()
    assert native.registry in registry


def test_older_install_without_desktop_receipt_preserves_unowned_desktop_link(tmp_path, monkeypatch):
    native, registry, desktop, _ = integration(tmp_path, monkeypatch)
    native.create()
    registry[native.registry].pop("ManagedDesktopShortcut")
    path = desktop / "ClipAI Preview.lnk"
    native.remove()
    assert path.exists()


def test_lifecycle_batches_four_workers_and_rechecks_changed_ownership(tmp_path, monkeypatch):
    native, registry, desktop, links = integration(tmp_path, monkeypatch)
    monkeypatch.delattr(native, "_shortcuts")
    calls = []
    def run(command, **kwargs):
        batch = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        calls.append((batch, native.registry in registry))
        for intent in batch:
            path = Path(intent["path"])
            if intent["create"]:
                links[path] = intent["arguments"]
                path.touch()
            elif links[path] != intent["arguments"]:
                return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(windows.subprocess, "run", run)
    native.create()
    native.validate_removal()
    path = desktop / "ClipAI Preview.lnk"
    links[path] = "changed after first proof"
    with pytest.raises(RuntimeError, match="shortcut_integration_failed"):
        native.remove()
    assert [(len(batch), registered) for batch, registered in calls] == [
        (2, False), (1, True), (3, True), (3, True)]
    assert path.exists() and native.registry in registry
    assert not (tmp_path / "shortcut-intent.json").exists()


@pytest.mark.parametrize("damage", ["empty", "oversized", "mixed", "duplicate", "malformed"])
def test_worker_admits_whole_batch_before_native_calls(tmp_path, monkeypatch, damage):
    from ClipAI.platform import windows_shell_link as worker
    intent = {"path": str(tmp_path / "a.lnk"), "target": str(tmp_path / "pythonw.exe"),
              "arguments": "-I launch", "icon": str(tmp_path / "icon.ico"), "create": True}
    batch = [intent, {**intent, "path": str(tmp_path / "b.lnk")}]
    if damage == "empty":
        batch = []
    elif damage == "oversized":
        batch *= 2
    elif damage == "mixed":
        batch[1]["create"] = False
    elif damage == "duplicate":
        batch[1]["path"] = intent["path"]
    else:
        batch[1]["target"] = "relative.exe"
    request = tmp_path / "request.json"
    request.write_text(json.dumps(batch), encoding="utf-8")
    calls = []
    monkeypatch.setattr(worker, "_apply", calls.append)
    monkeypatch.setattr(sys, "argv", [worker.__file__, str(request)])
    assert worker.main() == 1
    assert calls == []


def test_failed_start_menu_phase_does_not_publish_registry_or_desktop(tmp_path, monkeypatch):
    native, registry, desktop, _ = integration(tmp_path, monkeypatch)
    monkeypatch.delattr(native, "_shortcuts")
    calls = []
    def fail(command, **kwargs):
        batch = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        calls.append(batch)
        # A native batch is not atomic: its first link can already exist.
        Path(batch[0]["path"]).touch()
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(windows.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="shortcut_integration_failed"):
        native.create()
    assert len(calls) == 1 and len(calls[0]) == 2
    assert registry == {} and not list(desktop.iterdir())
    assert (native.group / "ClipAI Preview.lnk").exists()
    assert not (tmp_path / "shortcut-intent.json").exists()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != 'win32', reason='Windows shortcut adapter')
def test_native_unicode_shortcut_roundtrip_preserves_owned_arguments(tmp_path):
    import os
    import shutil

    root = tmp_path / '安裝 probe'
    root.mkdir()
    (root / 'runtime').mkdir()
    (root / 'setup-engine').mkdir()
    shutil.copy2(Path(sys.base_prefix) / 'pythonw.exe', root / 'runtime/pythonw.exe')
    shutil.copy2(Path(windows.__file__).resolve().parents[1] / 'ui/assets/clipai.ico', root / 'setup-engine/clipai.ico')
    environment = {key.upper(): value for key, value in os.environ.items()}
    environment['PATH'] = ''
    native = windows.WindowsInstallationIntegration(
        product='ClipAI Probe', registry_name='Probe', root=root, shared=root,
        install_id='probe', version='3.7.18', work_root=root, environment=environment)
    path = root / '測試.lnk'
    native._shortcuts(((path, 'launch'), (root / '移除.lnk', 'uninstall')), create=True)
    assert path.is_file()
    native._shortcuts(((path, 'launch'), (root / '移除.lnk', 'uninstall')), create=False)
    original_bytes = path.read_bytes()
    with pytest.raises(RuntimeError, match='shortcut_integration_failed'):
        native._shortcuts(((path, 'uninstall'),), create=False)
    assert path.read_bytes() == original_bytes
    assert not (root / 'shortcut-intent.json').exists()
