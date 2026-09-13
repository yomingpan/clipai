from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
import uuid

from ClipAI.app.application_lifecycle import build_application_instance_gate
from ClipAI.app.application_paths import build_application_paths, build_managed_application_paths
from ClipAI.app.language_pack_bootstrap import bootstrap_action_language_config
from ClipAI.app.container import build_runtime
from ClipAI.app.managed_command_executor import ManagedCommandExecutor
from ClipAI.app.managed_update_dispatcher import dispatch_managed_update
from ClipAI.app.managed_update_host import ManagedUpdateHostExecutor
from ClipAI.app.managed_update_launch import ManagedLaunchExecutor
from ClipAI.core.errors import ConfigError
from ClipAI.core.managed_update import launch_attempt_id
from ClipAI.core.managed_update_commands import (
    HostManagedCommand,
    InstallManagedCommand,
    LaunchManagedCommand,
    SelfcheckManagedCommand,
)
from ClipAI.core.ports import ApplicationInstanceGate
from ClipAI.core.update_ports import CandidateEnvironmentBuilder
from ClipAI.platform.action_language_selection import JsonActionLanguagePackSelectionStore
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.managed_install import DocumentVerifier
from ClipAI.platform.managed_installer import FilesystemManagedInstaller
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
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
    manifest_verifier: DocumentVerifier | None = None,
    candidate_builder: CandidateEnvironmentBuilder | None = None,
) -> int:
    app_root = Path(application_root or Path(__file__).resolve().parent).resolve()
    injected_environment = dict(os.environ if environment is None else environment)

    def verifier_for(command: InstallManagedCommand | HostManagedCommand) -> DocumentVerifier:
        if manifest_verifier is not None:
            return manifest_verifier
        ssh_keygen = shutil.which("ssh-keygen", path=injected_environment.get("PATH", ""))
        if ssh_keygen is None:
            raise ValueError("Windows OpenSSH ssh-keygen is required")
        keyring = load_trusted_release_keyring(app_root / "managed-update-trusted-keys.json")
        return Ed25519ManifestVerifier(
            ssh_keygen=ssh_keygen,
            trusted_keys=keyring.verification_keys(),
            work_root=command.shared_root / "managed-update" / "signature-verification",
            environment=injected_environment,
        )

    def builder_for() -> CandidateEnvironmentBuilder:
        return candidate_builder or OfflineCandidateEnvironmentBuilder(environment=injected_environment)

    def install(command: InstallManagedCommand) -> int:
        FilesystemManagedInstaller(
            manifest_verifier=verifier_for(command),
            candidate_builder=builder_for(),
        ).install(command)
        return 0

    def launch(command: LaunchManagedCommand) -> int:
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

    def host(command: HostManagedCommand) -> int:
        return ManagedUpdateHostExecutor(
            manifest_verifier=verifier_for(command),
            candidate_builder=builder_for(),
            environment=injected_environment,
            now=_utc_now,
            launch_attempt_factory=lambda: launch_attempt_id(f"attempt-{uuid.uuid4().hex}"),
        ).execute(command)

    def selfcheck(_command: SelfcheckManagedCommand) -> int:
        raise ValueError("managed selfcheck is not composed yet")

    executor = ManagedCommandExecutor(
        install=install,
        launch=launch,
        host=host,
        selfcheck=selfcheck,
    )
    return dispatch_managed_update(argv, executor.execute)


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
