from __future__ import annotations

from pathlib import Path

import pytest

from scripts import run_unit_tests


def test_environment_prefers_an_explicit_test_temp_root(tmp_path: Path) -> None:
    configured_root = tmp_path / "configured"

    environment = run_unit_tests.prepare_test_environment(
        tmp_path,
        environment={run_unit_tests.TEST_TEMP_ROOT_ENV: str(configured_root)},
    )

    assert environment.base_temp.parent == configured_root
    assert environment.cache_dir == configured_root / "cache"
    assert environment.cache_dir.is_dir()


def test_environment_falls_back_to_project_local_storage_when_system_temp_is_unavailable(tmp_path: Path) -> None:
    unavailable_temp = tmp_path / "not-a-directory"
    unavailable_temp.write_text("blocked", encoding="utf-8")

    environment = run_unit_tests.prepare_test_environment(
        tmp_path,
        environment={},
        temporary_directory=unavailable_temp,
    )

    assert environment.base_temp.parent == tmp_path / ".clipai-test-artifacts"


def test_explicit_unwritable_test_root_reports_an_actionable_error(tmp_path: Path) -> None:
    unavailable_root = tmp_path / "not-a-directory"
    unavailable_root.write_text("blocked", encoding="utf-8")

    with pytest.raises(run_unit_tests.TestEnvironmentError, match="CLIPAI_TEST_TEMP_ROOT"):
        run_unit_tests.prepare_test_environment(
            tmp_path,
            environment={run_unit_tests.TEST_TEMP_ROOT_ENV: str(unavailable_root)},
        )


def test_pytest_command_uses_isolated_base_temp_and_cache(tmp_path: Path) -> None:
    environment = run_unit_tests.TestEnvironment(
        base_temp=tmp_path / "run",
        cache_dir=tmp_path / "cache",
    )

    command = run_unit_tests.pytest_command(environment, ("tests/app", "-q"))

    assert command[1:3] == ["-m", "pytest"]
    assert command[3:5] == ["--basetemp", str(environment.base_temp)]
    assert command[5:7] == ["-o", f"cache_dir={environment.cache_dir}"]
    assert command[7:] == ["tests/app", "-q"]
