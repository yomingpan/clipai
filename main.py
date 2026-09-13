from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import multiprocessing
import os
from pathlib import Path
import sys

from ClipAI.app.application_lifecycle import build_application_instance_gate
from ClipAI.app.application_paths import build_application_paths, build_managed_application_paths
from ClipAI.app.language_pack_bootstrap import bootstrap_action_language_config
from ClipAI.app.container import build_runtime
from ClipAI.app.managed_update_dispatcher import dispatch_managed_update
from ClipAI.app.managed_update_launch import ManagedLaunchExecutor
from ClipAI.core.errors import ConfigError
from ClipAI.core.managed_update_commands import LaunchManagedCommand
from ClipAI.core.ports import ApplicationInstanceGate
from ClipAI.platform.action_language_selection import JsonActionLanguagePackSelectionStore
from ClipAI.ui.startup_error import show_startup_error

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def main(*, instance_gate: ApplicationInstanceGate | None = None) -> None:
    paths = build_application_paths(Path(__file__).resolve().parent, os.environ)
    _run_application(paths, instance_gate=instance_gate)


def managed_main(
    argv: Sequence[str],
    *,
    application_root: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
    actual_version: str | None = None,
    executable_path: str | Path | None = None,
    instance_gate: ApplicationInstanceGate | None = None,
) -> int:
    app_root = Path(application_root or Path(__file__).resolve().parent).resolve()
    injected_environment = dict(os.environ if environment is None else environment)

    def execute(command) -> int:
        if not isinstance(command, LaunchManagedCommand):
            raise ValueError("managed command is not composed yet")
        paths = build_managed_application_paths(
            app_root,
            command.shared_root,
            instance_name=injected_environment.get("CLIPAI_INSTANCE_NAME", "default").strip(),
        )
        return ManagedLaunchExecutor(
            actual_version=actual_version or _installed_version(),
            executable_path=executable_path or sys.executable,
            now=_utc_now,
            run_application=lambda on_started: _run_application(
                paths,
                instance_gate=instance_gate,
                on_started=on_started,
            ),
        ).execute(command)

    return dispatch_managed_update(argv, execute)


def _run_application(paths, *, instance_gate=None, on_started=None) -> None:
    instance_gate = instance_gate or build_application_instance_gate()
    instance_lease = instance_gate.acquire()
    if instance_lease is None:
        show_startup_error("ClipAI is already running.")
        return
    try:
        if load_dotenv:
            load_dotenv(paths.secrets_file, override=True)

        bootstrap = bootstrap_action_language_config(
            JsonActionLanguagePackSelectionStore(
                paths.state_file("action_language_pack.json")
            ),
            app_config_path=paths.config_file("config.yaml"),
            actions_path=paths.config_file("actions.yaml"),
            shortcuts_path=paths.config_file("shortcuts.yaml"),
            output_profiles_path=paths.config_file("output_profiles.yaml"),
            entry_panel_path=paths.config_file("entry_panel.yaml"),
        )
        runtime = build_runtime(bootstrap, paths=paths)
        if on_started is None:
            runtime.run_forever()
        else:
            runtime.run_forever(on_started=on_started)
    except ConfigError as exc:
        show_startup_error(str(exc))
        raise SystemExit(2) from None
    finally:
        if instance_lease is not None:
            instance_lease.close()


def _installed_version() -> str:
    try:
        return version("clipai")
    except PackageNotFoundError:
        return "development"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    arguments = sys.argv[1:]
    if arguments and arguments[0] in {"install", "launch", "host", "selfcheck"}:
        raise SystemExit(managed_main(arguments))
    main()
