from pathlib import Path

import pytest

from ClipAI.app.managed_update_dispatcher import dispatch_managed_update
from ClipAI.core.managed_update_commands import (
    HostManagedCommand,
    InstallManagedCommand,
    LaunchManagedCommand,
    SelfcheckManagedCommand,
)


def _roots(tmp_path: Path) -> list[str]:
    return [
        "--shared-root", str((tmp_path / "shared").resolve()),
        "--transaction-id", "tx-1",
        "--install-root", str((tmp_path / "install").resolve()),
    ]


def test_single_dispatcher_parses_all_four_typed_subcommands(tmp_path: Path):
    seen = []
    execute = lambda command: seen.append(command) or 17
    bundle = (tmp_path / "release.zip").resolve()
    base_python = (tmp_path / "python.exe").resolve()

    assert dispatch_managed_update([
        "install", *_roots(tmp_path),
        "--expected-version", "2.0",
        "--bundle-path", str(bundle),
        "--bundle-size", "42",
        "--bundle-sha256", "a" * 64,
        "--manifest-sha256", "b" * 64,
        "--key-id", "release-key",
        "--managed-install-id", "managed-1",
        "--launcher-version", "1.0",
        "--base-python", str(base_python),
    ], execute) == 17
    assert isinstance(seen[-1], InstallManagedCommand)
    assert seen[-1].bundle_path == bundle

    assert dispatch_managed_update([
        "launch", *_roots(tmp_path),
        "--launch-attempt-id", "attempt-1",
        "--expected-version", "2.0",
    ], execute) == 17
    assert isinstance(seen[-1], LaunchManagedCommand)

    dispatch_managed_update(["host", *_roots(tmp_path), "--base-python", str(base_python)], execute)
    assert isinstance(seen[-1], HostManagedCommand)
    dispatch_managed_update(["selfcheck", *_roots(tmp_path)], execute)
    assert isinstance(seen[-1], SelfcheckManagedCommand)


@pytest.mark.parametrize(
    "arguments",
    [
        ["selfcheck", "--shared-root", "relative", "--transaction-id", "tx", "--install-root", "C:\\install"],
        ["launch", "--shared-root", "C:\\shared", "--transaction-id", "../tx", "--install-root", "C:\\install", "--launch-attempt-id", "a", "--expected-version", "2.0"],
        ["launch", "--shared-root", "C:\\shared", "--transaction-id", "tx", "--install-root", "C:\\install", "--launch-attempt-id", "a", "--expected-version", "v2.0"],
    ],
)
def test_dispatcher_rejects_relative_paths_malformed_ids_and_noncanonical_versions(arguments: list[str]):
    with pytest.raises(SystemExit) as raised:
        dispatch_managed_update(arguments, lambda _command: 0)
    assert raised.value.code == 2
