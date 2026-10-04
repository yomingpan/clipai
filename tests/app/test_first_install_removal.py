import pytest

from ClipAI.app import first_install_bootstrap as bootstrap
from ClipAI.platform.managed_update_fs import atomic_write_json
from ClipAI.ui import installation_maintenance as maintenance


@pytest.mark.parametrize("choice", [False, True, None])
def test_windows_uninstall_choice_reaches_helper_without_implicit_deletion(tmp_path, monkeypatch, choice):
    atomic_write_json(tmp_path / "setup-engine/candidate.json", {"product": "Fixture"})
    calls = []
    monkeypatch.setattr(maintenance, "choose_uninstall", lambda _: choice)
    monkeypatch.setattr(bootstrap, "read_owner", lambda *_: {})
    monkeypatch.setattr(bootstrap, "start_maintenance_helper", lambda *args, **kwargs: calls.append(kwargs))
    assert bootstrap.main(["uninstall", "--install-root", str(tmp_path / "program"),
                           "--shared-root", str(tmp_path / "data")], bootstrap_root=tmp_path, environment={}) == 0
    assert len(calls) == (0 if choice is None else 1)
    if calls:
        assert calls[0]["delete_user_data"] is choice


@pytest.mark.parametrize("delete_data", [False, True])
def test_setup_worker_passes_exact_data_policy_to_backend(tmp_path, monkeypatch, delete_data):
    atomic_write_json(tmp_path / "setup-engine/candidate.json", {"product": "Fixture"})
    import time
    monkeypatch.setattr(time, "sleep", lambda _: None)
    intents = []
    class Backend:
        def remove(self, intent):
            intents.append(intent)
    monkeypatch.setattr(bootstrap, "FilesystemUninstaller", lambda _: Backend())
    arguments = ["remove-worker", "--quiet", "--install-root", str(tmp_path / "program"), "--shared-root", str(tmp_path / "data")]
    if delete_data:
        arguments.append("--delete-user-data")
    assert bootstrap.main(arguments, bootstrap_root=tmp_path, environment={}) == 0
    assert len(intents) == 1 and intents[0].delete_user_data is delete_data


def test_install_intent_cannot_request_data_deletion(tmp_path):
    with pytest.raises(SystemExit):
        bootstrap.main(["install", "--install-root", str(tmp_path / "program"),
                        "--shared-root", str(tmp_path / "data"), "--delete-user-data"],
                       bootstrap_root=tmp_path, environment={})
