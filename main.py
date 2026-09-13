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
from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.core.managed_update_commands import (
    HostManagedCommand,
    InstallManagedCommand,
    LaunchManagedCommand,
    SelfcheckManagedCommand,
)
from ClipAI.core.ports import ApplicationInstanceGate
from ClipAI.core.update_ports import CandidateEnvironmentBuilder
from ClipAI.core.update_artifacts import UpdateResultArtifact
from ClipAI.platform.action_language_selection import JsonActionLanguagePackSelectionStore
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.managed_install import DocumentVerifier, ManagedInstallLayout, read_stable_launcher_marker
from ClipAI.platform.managed_installer import FilesystemManagedInstaller
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
from ClipAI.platform.managed_update_lifecycle import SubprocessManagedApplicationLifecycle
from ClipAI.platform.managed_update_recovery import find_incomplete_update
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.services.managed_current_launch import ManagedCurrentLaunchCoordinator
from ClipAI.ui.startup_error import show_startup_error

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def main(*, instance_gate: ApplicationInstanceGate | None = None) -> None:
    app_root = _entry_application_root(Path(__file__).resolve())
    marker = read_stable_launcher_marker(app_root)
    if marker is not None:
        try:
            _launch_managed_current(app_root, marker, dict(os.environ))
        except Exception as exc:
            show_startup_error(f"Managed ClipAI could not start: {exc}")
        return
    paths = build_application_paths(app_root, os.environ)
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
    app_root = (
        Path(application_root).resolve()
        if application_root is not None
        else _entry_application_root(Path(__file__).resolve())
    )
    injected_environment = dict(os.environ if environment is None else environment)

    def verifier_for(
        command: InstallManagedCommand | HostManagedCommand | SelfcheckManagedCommand,
    ) -> DocumentVerifier:
        if manifest_verifier is not None:
            return manifest_verifier
        return _build_manifest_verifier(
            app_root,
            command.shared_root,
            injected_environment,
        )

    def builder_for() -> CandidateEnvironmentBuilder:
        return candidate_builder or OfflineCandidateEnvironmentBuilder(environment=injected_environment)

    def install(command: InstallManagedCommand) -> int:
        FilesystemManagedInstaller(
            manifest_verifier=verifier_for(command),
            candidate_builder=builder_for(),
            trusted_keyring_path=app_root / "managed-update-trusted-keys.json",
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

    def selfcheck(command: SelfcheckManagedCommand) -> int:
        try:
            ManagedInstallLayout(
                install_root=command.install_root,
                shared_root=command.shared_root,
                manifest_verifier=verifier_for(command),
            ).prove_current_install()
        except Exception:
            return 1
        return 0

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


def _entry_application_root(entrypoint: Path) -> Path:
    root = entrypoint.parent
    if root.name.casefold() == "payload" and root.parent.name.casefold() == "launcher":
        return root.parent
    return root


def _build_manifest_verifier(
    app_root: Path,
    shared_root: Path,
    environment: Mapping[str, str],
) -> DocumentVerifier:
    ssh_keygen = shutil.which("ssh-keygen", path=environment.get("PATH", ""))
    if ssh_keygen is None:
        raise ValueError("Windows OpenSSH ssh-keygen is required")
    keyring = load_trusted_release_keyring(app_root / "managed-update-trusted-keys.json")
    return Ed25519ManifestVerifier(
        ssh_keygen=ssh_keygen,
        trusted_keys=keyring.verification_keys(),
        work_root=shared_root / "managed-update" / "signature-verification",
        environment=environment,
    )


def _launch_managed_current(app_root, marker, environment: Mapping[str, str]) -> None:
    verifier = _build_manifest_verifier(app_root, marker.shared_root, environment)
    layout = ManagedInstallLayout(
        install_root=marker.install_root,
        shared_root=marker.shared_root,
        manifest_verifier=verifier,
    )
    lifecycle = SubprocessManagedApplicationLifecycle(
        layout=layout,
        environment=environment,
        shutdown=lambda _transaction_id: None,
        now=_utc_now,
    )
    interrupted = find_incomplete_update(marker.shared_root)
    if interrupted is not None:
        base_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        result_code = ManagedUpdateHostExecutor(
            manifest_verifier=verifier,
            candidate_builder=OfflineCandidateEnvironmentBuilder(environment=environment),
            environment=environment,
            now=_utc_now,
            launch_attempt_factory=lambda: launch_attempt_id(f"recovery-{uuid.uuid4().hex}"),
        ).execute(HostManagedCommand(
            marker.shared_root,
            marker.install_root,
            interrupted,
            base_python,
        ))
        result = ManagedUpdateArtifactStore(
            shared_root=marker.shared_root,
            transaction_id=str(interrupted),
        ).read("result")
        if not isinstance(result, UpdateResultArtifact):
            raise RuntimeError("managed recovery result has wrong type")
        if result.outcome == "rolled_back":
            return
        raise RuntimeError(
            f"managed recovery failed with {result.rollback_failure_code or result.failure_code}; exit={result_code}"
        )
    ManagedCurrentLaunchCoordinator(
        install=layout,
        lifecycle=lifecycle,
        transaction_id_factory=lambda: transaction_id(f"startup-{uuid.uuid4().hex}"),
        launch_attempt_factory=lambda: launch_attempt_id(f"attempt-{uuid.uuid4().hex}"),
    ).execute()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    arguments = sys.argv[1:]
    if arguments and arguments[0] in {"install", "launch", "host", "selfcheck"}:
        raise SystemExit(managed_main(arguments))
    main()
