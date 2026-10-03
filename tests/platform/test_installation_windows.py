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
