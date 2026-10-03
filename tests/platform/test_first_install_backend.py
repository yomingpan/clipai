from pathlib import Path

import pytest

from ClipAI.platform import first_install_backend as backend
from ClipAI.platform.managed_update_fs import atomic_write_json


def test_uninstall_rejects_changed_native_identity_before_deleting_payload(tmp_path: Path, monkeypatch) -> None:
    root, shared = tmp_path / "program", tmp_path / "retained"
    root.mkdir()
    payload = root / "runtime" / "owned.txt"
    payload.parent.mkdir()
    payload.write_text("must survive failed native ownership proof", encoding="utf-8")
    owner = {"schema_version": 1, "owner_kind": backend.OWNER_KIND,
             "install_root": str(root), "shared_root": str(shared),
             "owned_directories": list(backend.OWNED_DIRECTORIES), "owned_files": list(backend.OWNED_FILES),
             "transaction_id": "install-test", "managed_install_id": "test-install",
             "product": "ClipAI Preview", "registry_name": "ClipAI.Preview",
             "version": "3.7.8", "phase": "installed"}
    atomic_write_json(root / "first-install-owner.json", owner)

    class Admission:
        closed = False

        def close(self):
            self.closed = True

    class ChangedIntegration:
        def __init__(self, **keywords):
            pass

        def validate_removal(self):
            raise RuntimeError("uninstall_registration_identity_changed")

    admission = Admission()
    monkeypatch.setattr(backend, "admit_installation", lambda _root: admission)
    monkeypatch.setattr(backend, "assert_installation_idle", lambda _root: None)
    monkeypatch.setattr(backend, "WindowsInstallationIntegration", ChangedIntegration)
    with pytest.raises(RuntimeError, match="identity_changed"):
        backend.uninstall_owned_installation(root, shared, environment={})
    assert payload.read_text(encoding="utf-8") == "must survive failed native ownership proof"
    assert (root / "first-install-owner.json").is_file()
    assert admission.closed


def test_busy_uninstall_leaves_payload_and_owner_untouched(tmp_path: Path, monkeypatch) -> None:
    from ClipAI.core.first_install import InstallationBusyError

    root, shared = tmp_path / "program", tmp_path / "retained"
    root.mkdir()
    payload = root / "runtime" / "owned.txt"
    payload.parent.mkdir()
    payload.write_text("still in use", encoding="utf-8")
    owner = {"schema_version": 1, "owner_kind": backend.OWNER_KIND,
             "install_root": str(root), "shared_root": str(shared),
             "owned_directories": list(backend.OWNED_DIRECTORIES), "owned_files": list(backend.OWNED_FILES),
             "transaction_id": "busy-test", "managed_install_id": "busy-install",
             "product": "ClipAI Preview", "registry_name": "ClipAI.Preview",
             "version": "3.7.8", "phase": "installed"}
    atomic_write_json(root / "first-install-owner.json", owner)
    original_owner = (root / "first-install-owner.json").read_bytes()
    class Admission:
        closed = False
        def close(self):
            self.closed = True
    def busy(_root):
        raise InstallationBusyError()
    admission = Admission()
    monkeypatch.setattr(backend, "admit_installation", lambda _root: admission)
    monkeypatch.setattr(backend, "assert_installation_idle", busy)
    with pytest.raises(InstallationBusyError):
        backend.uninstall_owned_installation(root, shared, environment={})
    assert payload.read_text(encoding="utf-8") == "still in use"
    assert (root / "first-install-owner.json").read_bytes() == original_owner
    assert admission.closed
