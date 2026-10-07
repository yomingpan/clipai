from contextlib import nullcontext
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
    def shortcut(path, action, *, create):
        if create:
            links[path] = action
            path.touch()
        elif links[path] != action:
            raise RuntimeError("Shortcut ownership changed")
    monkeypatch.setattr(result, "_shortcut", shortcut)
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


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != 'win32', reason='Windows shortcut adapter')
def test_native_shortcut_roundtrip_without_module_autoload(tmp_path, monkeypatch):
    import base64
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
    original = windows.subprocess.run
    call_count = 0

    def no_autoload(command, **kwargs):
        nonlocal call_count
        call_count += 1
        code = base64.b64decode(command[-1]).decode('utf-16-le')
        code = "$PSModuleAutoLoadingPreference = 'None'\n" + code
        command = [*command[:-1], base64.b64encode(code.encode('utf-16-le')).decode()]
        result = original(command, **kwargs)
        if call_count <= 2:
            assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')[-3000:]
        return result

    monkeypatch.setattr(windows.subprocess, 'run', no_autoload)
    path = root / '測試.lnk'
    native._shortcut(path, 'launch', create=True)
    assert path.is_file()
    native._shortcut(path, 'launch', create=False)
    original_bytes = path.read_bytes()
    with pytest.raises(RuntimeError, match='shortcut_integration_failed'):
        native._shortcut(path, 'uninstall', create=False)
    assert path.read_bytes() == original_bytes
    assert not (root / 'shortcut-intent.json').exists()
