from __future__ import annotations

from pathlib import Path
import pytest
from types import SimpleNamespace

from ClipAI.core.errors import ConfigError
from ClipAI.core.managed_update import transaction_id
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.managed_update_fs import read_json
import main


class Lease:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class InstanceGate:
    def __init__(self, lease: Lease | None) -> None:
        self.lease = lease

    def acquire(self) -> Lease | None:
        return self.lease


class ManifestSigner:
    def sign(self, manifest: bytes) -> bytes:
        return b"synthetic:" + manifest[:16]


class ManifestVerifier:
    def verify(self, manifest_path, signature_path, *, key_id):
        return None


class CandidateBuilder:
    def build(self, request):
        python = request.candidate_root / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        return CandidateEnvironment(
            request.candidate_root,
            python,
            request.candidate_root / request.entrypoint,
            request.expected_version,
        )


def test_config_error_uses_startup_error_surface(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(main, "load_dotenv", None)
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store, **_paths: (_ for _ in ()).throw(ConfigError("bad config")))
    monkeypatch.setattr(main, "show_startup_error", messages.append)

    with pytest.raises(SystemExit) as caught:
        main.main(instance_gate=InstanceGate(Lease()))

    assert caught.value.code == 2
    assert messages == ["bad config"]


def test_main_loads_dotenv_with_file_precedence(monkeypatch) -> None:
    calls: list[tuple[object, bool]] = []
    runtime = type("Runtime", (), {"run_forever": lambda self: None})()
    monkeypatch.setattr(main, "load_dotenv", lambda path, *, override: calls.append((path, override)))
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store, **_paths: SimpleNamespace(bundle=object()))
    monkeypatch.setattr(main, "build_runtime", lambda _bundle, *, paths: runtime)

    main.main(instance_gate=InstanceGate(Lease()))

    assert len(calls) == 1
    assert calls[0][0].name == ".env"
    assert calls[0][1] is True


def test_second_instance_stops_before_loading_configuration(monkeypatch) -> None:
    messages: list[str] = []
    configuration_loads: list[str] = []
    monkeypatch.setattr(main, "show_startup_error", messages.append)
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store: configuration_loads.append("loaded"))

    main.main(instance_gate=InstanceGate(None))

    assert configuration_loads == []
    assert messages == ["ClipAI is already running."]


def test_main_uses_composed_instance_gate_before_loading_configuration(monkeypatch) -> None:
    configuration_loads: list[str] = []
    runtime = type("Runtime", (), {"run_forever": lambda self: None})()

    def load_configuration():
        configuration_loads.append("loaded")
        return object()

    monkeypatch.setattr(main, "build_application_instance_gate", lambda: InstanceGate(None), raising=False)
    monkeypatch.setattr(main, "show_startup_error", lambda _message: None)
    monkeypatch.setattr(main, "load_dotenv", None)
    monkeypatch.setattr(main, "bootstrap_action_language_config", lambda _store: SimpleNamespace(bundle=load_configuration()))
    monkeypatch.setattr(main, "build_runtime", lambda _bundle: runtime)

    main.main()

    assert configuration_loads == []


def test_managed_launch_cli_uses_explicit_paths_and_reports_runtime_readiness(monkeypatch, tmp_path) -> None:
    application_root = (tmp_path / "install" / "versions" / "2.0" / "payload").resolve()
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared" / "instances" / "sandbox").resolve()
    executable = (install_root / "versions" / "2.0" / ".venv" / "Scripts" / "python.exe").resolve()
    observed_paths = []

    class Runtime:
        def run_forever(self, *, on_started):
            assert not ManagedUpdateArtifactStore(
                shared_root=shared_root,
                transaction_id="tx-1",
            ).path("startup_health").exists()
            on_started()

    monkeypatch.setattr(main, "load_dotenv", None)
    monkeypatch.setattr(
        main,
        "bootstrap_action_language_config",
        lambda _store, **_paths: SimpleNamespace(bundle=object()),
    )
    monkeypatch.setattr(
        main,
        "build_runtime",
        lambda _bootstrap, *, paths: observed_paths.append(paths) or Runtime(),
    )

    exit_code = main.managed_main(
        [
            "launch",
            "--shared-root", str(shared_root),
            "--transaction-id", "tx-1",
            "--install-root", str(install_root),
            "--launch-attempt-id", "attempt-1",
            "--expected-version", "2.0",
        ],
        application_root=application_root,
        environment={"CLIPAI_INSTANCE_NAME": "sandbox"},
        actual_version="2.0",
        executable_path=executable,
        instance_gate=InstanceGate(Lease()),
    )

    assert exit_code == 0
    assert observed_paths[0].application_root == application_root
    assert observed_paths[0].state_root == shared_root / "state"
    health = ManagedUpdateArtifactStore(shared_root=shared_root, transaction_id="tx-1").read("startup_health")
    assert health.healthy is True
    assert health.executable_path == executable


def _install_managed_version(tmp_path: Path) -> tuple[int, Path, Path, Path]:
    launcher_root = (tmp_path / "stable-launcher").resolve()
    launcher_root.mkdir()
    (launcher_root / "managed-update-trusted-keys.json").write_text(
        '{"bootstrap":"trusted"}\n', encoding="utf-8"
    )
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('installed')\n", encoding="utf-8")
    (wheelhouse / "clipai.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==2.0\n", encoding="utf-8")
    bundle = ManagedReleaseBuilder(ManifestSigner()).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=lock,
        output_path=tmp_path / "release.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.11",
        key_id="release-key",
    )
    base_python = (tmp_path / "base-python.exe").resolve()
    base_python.write_bytes(b"")

    exit_code = main.managed_main(
        [
            "install",
            "--shared-root", str(shared_root),
            "--transaction-id", str(transaction_id("tx-install")),
            "--install-root", str(install_root),
            "--expected-version", "2.0",
            "--bundle-path", str(bundle.bundle_path),
            "--bundle-size", str(bundle.bundle_size),
            "--bundle-sha256", bundle.bundle_sha256,
            "--manifest-sha256", bundle.manifest_sha256,
            "--key-id", "release-key",
            "--managed-install-id", "managed-1",
            "--launcher-version", "1.0",
            "--base-python", str(base_python),
        ],
        application_root=launcher_root,
        environment={},
        manifest_verifier=ManifestVerifier(),
        candidate_builder=CandidateBuilder(),
    )
    return exit_code, launcher_root, install_root, shared_root


def _write_installed_distribution_metadata(install_root: Path) -> None:
    distribution = (
        install_root
        / "versions"
        / "2.0"
        / ".venv"
        / "Lib"
        / "site-packages"
        / "clipai-2.0.dist-info"
    )
    distribution.mkdir(parents=True)
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: ClipAI\nVersion: 2.0\n",
        encoding="utf-8",
    )


def test_managed_install_cli_publishes_verified_initial_install_without_launching(tmp_path) -> None:
    exit_code, _launcher_root, install_root, _shared_root = _install_managed_version(tmp_path)

    assert exit_code == 0
    assert read_json(install_root / "install-state.json")["current_version"] == "2.0"
    assert read_json(install_root / "managed-install.json")["managed_install_id"] == "managed-1"
    assert (install_root / "launcher" / "managed-update-trusted-keys.json").is_file()


def test_stable_launcher_entrypoint_resolves_fixed_root_and_delegates_current_launch(monkeypatch, tmp_path) -> None:
    launcher_root = (tmp_path / "install" / "launcher").resolve()
    entrypoint = launcher_root / "payload" / "main.py"
    versioned_entrypoint = tmp_path / "install" / "versions" / "2.0" / "payload" / "main.py"
    assert main._entry_application_root(entrypoint) == launcher_root
    assert main._entry_application_root(versioned_entrypoint) == versioned_entrypoint.parent

    marker = SimpleNamespace(shared_root=(tmp_path / "shared").resolve())
    calls = []
    monkeypatch.setattr(main, "_entry_application_root", lambda _entrypoint: launcher_root)
    monkeypatch.setattr(main, "read_stable_launcher_marker", lambda root: marker if root == launcher_root else None)
    monkeypatch.setattr(main, "_launch_managed_current", lambda root, identity, environment: calls.append((root, identity, environment)))
    monkeypatch.setattr(main, "build_application_paths", lambda *_args: (_ for _ in ()).throw(AssertionError("must not enter source runtime")))

    main.main()

    assert calls and calls[0][0:2] == (launcher_root, marker)


def test_managed_selfcheck_cli_proves_current_version_without_mutating_state(tmp_path) -> None:
    _exit_code, launcher_root, install_root, shared_root = _install_managed_version(tmp_path)
    _write_installed_distribution_metadata(install_root)
    state_before = read_json(install_root / "install-state.json")

    exit_code = main.managed_main(
        [
            "selfcheck",
            "--shared-root", str(shared_root),
            "--transaction-id", "tx-selfcheck",
            "--install-root", str(install_root),
        ],
        application_root=launcher_root,
        environment={},
        manifest_verifier=ManifestVerifier(),
    )

    assert exit_code == 0
    assert read_json(install_root / "install-state.json") == state_before


def test_managed_selfcheck_cli_fails_closed_without_repairing_missing_entrypoint(tmp_path) -> None:
    _exit_code, launcher_root, install_root, shared_root = _install_managed_version(tmp_path)
    _write_installed_distribution_metadata(install_root)
    state_before = read_json(install_root / "install-state.json")
    (install_root / "versions" / "2.0" / "payload" / "main.py").unlink()

    exit_code = main.managed_main(
        [
            "selfcheck",
            "--shared-root", str(shared_root),
            "--transaction-id", "tx-selfcheck-failed",
            "--install-root", str(install_root),
        ],
        application_root=launcher_root,
        environment={},
        manifest_verifier=ManifestVerifier(),
    )

    assert exit_code == 1
    assert read_json(install_root / "install-state.json") == state_before
