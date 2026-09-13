from pathlib import Path

import pytest

from ClipAI.app.application_paths import (
    build_application_paths,
    build_managed_application_paths,
    resolve_runtime_file,
)


def test_source_paths_preserve_existing_layout_with_absolute_ownership(tmp_path: Path):
    local_app_data = tmp_path / "local-app-data"
    paths = build_application_paths(tmp_path, {"LOCALAPPDATA": str(local_app_data)})
    assert paths.config_root == tmp_path / "config"
    assert paths.state_root == tmp_path / "data"
    assert paths.secrets_file == tmp_path / ".env"
    assert paths.config_root != paths.state_root
    assert paths.recent_actions_file == local_app_data / "ClipAI" / "recent_actions.json"


def test_managed_shared_paths_are_separate_from_version_payload(tmp_path: Path):
    version_root = tmp_path / "install" / "versions" / "3.8.0"
    shared_root = tmp_path / "shared"
    paths = build_application_paths(
        version_root,
        {"CLIPAI_SHARED_ROOT": str(shared_root), "CLIPAI_INSTANCE_NAME": "update-sandbox"},
    )
    instance_root = shared_root / "instances" / "update-sandbox"
    assert paths.config_root == version_root / "config"
    assert paths.state_root == instance_root / "state"
    assert paths.update_root == instance_root / "update"
    assert paths.secrets_file == instance_root / "secrets" / ".env"
    assert paths.recent_actions_file == instance_root / "state" / "recent_actions.json"


def test_managed_cli_shared_root_is_effective_and_never_gets_instance_appended_twice(tmp_path: Path):
    application_root = (tmp_path / "install" / "versions" / "3.8.0" / "payload").resolve()
    effective_shared_root = (tmp_path / "shared" / "instances" / "update-sandbox").resolve()

    paths = build_managed_application_paths(
        application_root,
        effective_shared_root,
        instance_name="update-sandbox",
    )

    assert paths.application_root == application_root
    assert paths.config_root == application_root / "config"
    assert paths.state_root == effective_shared_root / "state"
    assert paths.secrets_file == effective_shared_root / "secrets" / ".env"
    assert paths.update_root == effective_shared_root / "update"
    assert "instances\\update-sandbox\\instances" not in str(paths.state_root)


def test_invalid_instance_name_fails_before_any_path_is_used(tmp_path: Path):
    with pytest.raises(ValueError, match="CLIPAI_INSTANCE_NAME"):
        build_application_paths(tmp_path, {"CLIPAI_INSTANCE_NAME": "../escape"})


def test_managed_shared_root_must_be_absolute_and_outside_payload(tmp_path: Path):
    with pytest.raises(ValueError, match="must be absolute"):
        build_application_paths(tmp_path, {"CLIPAI_SHARED_ROOT": "relative"})
    with pytest.raises(ValueError, match="outside"):
        build_application_paths(
            tmp_path,
            {"CLIPAI_SHARED_ROOT": str(tmp_path / "shared")},
        )


def test_legacy_runtime_path_is_rebased_once():
    root = Path("C:/shared/logs")
    assert resolve_runtime_file("logs/clipai.log", root, "logs") == root / "clipai.log"
