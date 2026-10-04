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


@pytest.fixture
def removal_fixture(tmp_path, monkeypatch):
    root = tmp_path / "Programs/ClipAI Candidate"
    shared = tmp_path / "ClipAI Candidate"
    root.mkdir(parents=True)
    (root / "runtime").mkdir()
    (root / "runtime/owned.txt").write_text("runtime")
    (shared / "config").mkdir(parents=True)
    (shared / "config/.env").write_text("synthetic-key")
    (shared / "logs").mkdir()
    (shared / "logs/log.txt").write_text("synthetic log")
    owner = {"schema_version": 1, "owner_kind": backend.OWNER_KIND,
             "install_root": str(root), "shared_root": str(shared),
             "owned_directories": list(backend.OWNED_DIRECTORIES), "owned_files": list(backend.OWNED_FILES),
             "transaction_id": "install-test", "managed_install_id": "test-install",
             "product": "ClipAI Candidate", "registry_name": "ClipAI.LocalAcceptance.Candidate",
             "version": "3.7.8", "phase": "installed"}
    atomic_write_json(root / "first-install-owner.json", owner)
    class Admission:
        closed = False
        def close(self):
            self.closed = True
    class Integration:
        removed = False
        def __init__(self, **kwargs):
            self.work = kwargs["work_root"]
        def validate_removal(self):
            # Real native validation persists a shortcut request. Check full
            # deletion happens after the last native write, not before it.
            atomic_write_json(self.work / "shortcut-intent.json", {})
        def remove(self):
            self.validate_removal()
            Integration.removed = True
    admission = Admission()
    monkeypatch.setattr(backend, "admit_installation", lambda _: admission)
    monkeypatch.setattr(backend, "assert_installation_idle", lambda _: None)
    monkeypatch.setattr(backend, "WindowsInstallationIntegration", Integration)
    return root, shared, {"LOCALAPPDATA": str(tmp_path)}, owner, admission, Integration


@pytest.mark.parametrize("delete_data", [False, True])
def test_removal_policy_deletes_only_explicitly_selected_data(removal_fixture, delete_data):
    root, shared, environment, _, admission, integration = removal_fixture
    unrelated = root.parent / "Unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep")
    backend.uninstall_owned_installation(root, shared, environment=environment, delete_user_data=delete_data)
    assert not root.exists()
    assert shared.exists() is not delete_data
    if not delete_data:
        assert (shared / "config/.env").read_text() == "synthetic-key"
        assert (shared / "logs/log.txt").read_text() == "synthetic log"
    assert (unrelated / "keep.txt").read_text() == "keep"
    assert admission.closed and integration.removed


def test_full_removal_data_failure_preserves_retry_owner(removal_fixture, monkeypatch):
    root, shared, environment, _, admission, _ = removal_fixture
    real_remove = backend.remove_tree
    def fail_shared(path):
        if path == shared:
            raise PermissionError("fixture locked data")
        real_remove(path)
    monkeypatch.setattr(backend, "remove_tree", fail_shared)
    with pytest.raises(PermissionError):
        backend.uninstall_owned_installation(root, shared, environment=environment, delete_user_data=True)
    assert (root / "first-install-owner.json").exists()
    assert (shared / "config/.env").exists()
    assert admission.closed
    monkeypatch.setattr(backend, "remove_tree", real_remove)
    backend.uninstall_owned_installation(root, shared, environment=environment, delete_user_data=True)
    assert not root.exists() and not shared.exists()


@pytest.mark.parametrize("invalid", ["root", "identity", "unknown_program_file", "other_installation"])
def test_full_removal_refuses_ambiguous_ownership(removal_fixture, invalid):
    root, shared, environment, owner, _, _ = removal_fixture
    if invalid == "root":
        environment["LOCALAPPDATA"] = str(root.parent)
    elif invalid == "identity":
        atomic_write_json(root / "first-install-owner.json", {**owner, "registry_name": "OtherApp"})
    elif invalid == "unknown_program_file":
        (root / "other-user-file.txt").write_text("keep")
    else:
        atomic_write_json(shared / "managed-update/transactions/other/initial-install.json",
                          {**owner, "install_root": str(root.parent / "OtherApp")})
    with pytest.raises(ValueError):
        backend.uninstall_owned_installation(root, shared, environment=environment, delete_user_data=True)
    assert (root / "runtime/owned.txt").exists()
    assert (shared / "config/.env").exists()


def test_full_removal_refuses_redirected_data(removal_fixture, tmp_path):
    root, shared, environment, _, _, _ = removal_fixture
    outside = tmp_path / "unrelated-data"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    # Junction creation is available to a standard Windows user.
    import os
    import subprocess
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(shared / "redirect"), str(outside)], check=True, capture_output=True)
    else:
        (shared / "redirect").symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="redirected"):
            backend.uninstall_owned_installation(root, shared, environment=environment, delete_user_data=True)
        assert (outside / "keep.txt").read_text() == "keep"
        assert (root / "runtime/owned.txt").exists()
    finally:
        if os.name == "nt":
            (shared / "redirect").rmdir()
        else:
            (shared / "redirect").unlink()


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
