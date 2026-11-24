from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import re

from packaging.version import InvalidVersion, Version

from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.core.managed_update_commands import (
    HostManagedCommand,
    InstallManagedCommand,
    LaunchManagedCommand,
    ManagedCommand,
    SelfcheckManagedCommand,
)
from ClipAI.platform.update_catalog import MAX_BUNDLE_SIZE


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def dispatch_managed_update(
    argv: Sequence[str],
    execute: Callable[[ManagedCommand], int],
) -> int:
    """Parse the only managed entry interface and invoke one composed executor."""
    namespace = _parser().parse_args(list(argv))
    command = _command(namespace)
    return execute(command)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipai-managed")
    subcommands = parser.add_subparsers(dest="command", required=True)

    install = subcommands.add_parser("install")
    _roots_and_transaction(install)
    install.add_argument("--expected-version", required=True, type=_version)
    install.add_argument("--bundle-path", required=True, type=_absolute_path)
    install.add_argument("--bundle-size", required=True, type=_bundle_size)
    install.add_argument("--bundle-sha256", required=True, type=_sha256)
    install.add_argument("--manifest-sha256", required=True, type=_sha256)
    install.add_argument("--key-id", required=True, type=_identity)
    install.add_argument("--managed-install-id", required=True, type=_identity)
    install.add_argument("--launcher-version", required=True, type=_version)
    install.add_argument("--base-python", required=True, type=_absolute_path)

    launch = subcommands.add_parser("launch")
    _roots_and_transaction(launch)
    launch.add_argument("--launch-attempt-id", required=True, type=_launch_attempt)
    launch.add_argument("--expected-version", required=True, type=_version)

    host = subcommands.add_parser("host")
    _roots_and_transaction(host)
    host.add_argument("--base-python", required=True, type=_absolute_path)

    selfcheck = subcommands.add_parser("selfcheck")
    _roots_and_transaction(selfcheck)
    return parser


def _roots_and_transaction(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--shared-root", required=True, type=_absolute_path)
    parser.add_argument("--transaction-id", required=True, type=_transaction)
    parser.add_argument("--install-root", required=True, type=_absolute_path)


def _command(namespace: argparse.Namespace) -> ManagedCommand:
    common = {
        "shared_root": namespace.shared_root,
        "install_root": namespace.install_root,
        "transaction_id": namespace.transaction_id,
    }
    if namespace.command == "install":
        return InstallManagedCommand(
            **common,
            expected_version=namespace.expected_version,
            bundle_path=namespace.bundle_path,
            bundle_size=namespace.bundle_size,
            bundle_sha256=namespace.bundle_sha256,
            manifest_sha256=namespace.manifest_sha256,
            key_id=namespace.key_id,
            managed_install_id=namespace.managed_install_id,
            launcher_version=namespace.launcher_version,
            base_python=namespace.base_python,
        )
    if namespace.command == "launch":
        return LaunchManagedCommand(
            **common,
            launch_attempt_id=namespace.launch_attempt_id,
            expected_version=namespace.expected_version,
        )
    if namespace.command == "host":
        return HostManagedCommand(**common, base_python=namespace.base_python)
    return SelfcheckManagedCommand(**common)


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path.resolve()


def _version(value: str) -> str:
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise argparse.ArgumentTypeError("version must be PEP 440") from exc
    if str(parsed) != value:
        raise argparse.ArgumentTypeError("version must be normalized")
    return value


def _sha256(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("hash must be lowercase SHA-256")
    return value


def _identity(value: str) -> str:
    if _IDENTITY.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("identity is invalid")
    return value


def _transaction(value: str):
    try:
        return transaction_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _launch_attempt(value: str):
    try:
        return launch_attempt_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _bundle_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bundle size must be an integer") from exc
    if parsed <= 0 or parsed > MAX_BUNDLE_SIZE:
        raise argparse.ArgumentTypeError("bundle size is outside the supported range")
    return parsed
