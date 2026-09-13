from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ClipAI.app.managed_update_host import ManagedUpdateHostExecutor
from ClipAI.core.managed_update import FailureCode, launch_attempt_id, transaction_id
from ClipAI.core.managed_update_commands import HostManagedCommand
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder
from ClipAI.platform.managed_process import ManagedProcessIdentityError
from ClipAI.platform.managed_update_fs import atomic_write_json, read_json
from ClipAI.platform.managed_update_lifecycle import StartupHealthReporter
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore


NOW = "2026-09-13T00:00:00+00:00"


class _Signer:
    def sign(self, manifest: bytes) -> bytes:
        return b"synthetic:" + manifest[:16]


class _Verifier:
    def verify(self, manifest_path, signature_path, *, key_id):
        return None


class _CandidateBuilder:
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


class _InstalledProcess:
    def __init__(self, request: UpdateRequestArtifact) -> None:
        self.request = request
        self.waited = False
        self.closed = False

    def wait_for_exit(self, *, timeout_sec: float) -> None:
        assert timeout_sec == 20.0
        store = ManagedUpdateArtifactStore(
            shared_root=self.request.shared_root,
            transaction_id=str(self.request.transaction_id),
        )
        assert store.read("handoff_ready").expected_version == "2.0"
        state = read_json(self.request.install_root / "install-state.json")
        assert state["current_version"] == "1.0"
        self.waited = True

    def close(self) -> None:
        self.closed = True


class _BusyGate:
    def acquire(self):
        return None


class _Lease:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FreeGate:
    def __init__(self, lease: _Lease) -> None:
        self.lease = lease

    def acquire(self):
        return self.lease


def _write_current_install(install_root: Path, shared_root: Path) -> Path:
    current = install_root / "versions" / "1.0"
    python = current / ".venv" / "Scripts" / "python.exe"
    metadata = current / ".venv" / "Lib" / "site-packages" / "clipai-1.0.dist-info" / "METADATA"
    python.parent.mkdir(parents=True)
    metadata.parent.mkdir(parents=True)
    python.write_bytes(b"")
    metadata.write_text("Metadata-Version: 2.1\nName: ClipAI\nVersion: 1.0\n", encoding="utf-8")
    (current / "app.py").write_text("print('old')\n", encoding="utf-8")
    atomic_write_json(current / "install-manifest.json", {
        "schema_version": 1,
        "app_version": "1.0",
        "bundle_format": "clipai-managed-v1",
        "entrypoint": "app.py",
        "python_requires": ">=3.11",
        "requirements_lock_sha256": "a" * 64,
        "files": [
            {"path": "app.py", "size": 13, "sha256": "b" * 64, "role": "payload"},
            {"path": "requirements.lock", "size": 0, "sha256": "a" * 64, "role": "metadata"},
            {"path": "wheelhouse/clipai.whl", "size": 0, "sha256": "c" * 64, "role": "wheel"},
        ],
        "signing_namespace": "clipai.managed-update.manifest.v1",
        "key_id": "release-key",
    })
    atomic_write_json(install_root / "managed-install.json", {
        "schema_version": 1,
        "marker_kind": "clipai-managed-install-v1",
        "managed_install_id": "managed-1",
        "install_root": str(install_root),
        "shared_root": str(shared_root),
        "launcher_version": "1.0",
        "key_id": "release-key",
    })
    atomic_write_json(install_root / "install-state.json", {
        "schema_version": 1,
        "state_kind": "clipai-managed-install-state-v1",
        "managed_install_id": "managed-1",
        "revision": 0,
        "current_version": "1.0",
        "previous_version": None,
    })
    return python


def _write_request(tmp_path: Path) -> tuple[HostManagedCommand, UpdateRequestArtifact]:
    install_root = (tmp_path / "install").resolve()
    shared_root = (tmp_path / "shared").resolve()
    installed_python = _write_current_install(install_root, shared_root)
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    (payload / "main.py").write_text("print('new')\n", encoding="utf-8")
    (wheelhouse / "clipai.whl").write_bytes(b"wheel")
    lock = tmp_path / "requirements.lock"
    lock.write_text("clipai==2.0\n", encoding="utf-8")
    built = ManagedReleaseBuilder(_Signer()).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=lock,
        output_path=shared_root / "managed-update" / "transactions" / "tx-1" / "release.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.11",
        key_id="release-key",
    )
    request = UpdateRequestArtifact(
        transaction_id("tx-1"), NOW, "1.0", "2.0", installed_python, 1234,
        built.bundle_path, built.bundle_size, built.bundle_sha256,
        built.manifest_sha256, "release-key", install_root, shared_root, "managed-1",
    )
    ManagedUpdateArtifactStore(shared_root=shared_root, transaction_id="tx-1").write(request)
    base_python = (tmp_path / "base-python.exe").resolve()
    base_python.write_bytes(b"")
    return HostManagedCommand(shared_root, install_root, transaction_id("tx-1"), base_python), request


def test_host_executes_verified_transaction_and_publishes_updated_result(tmp_path: Path):
    command, request = _write_request(tmp_path)
    installed_processes: list[_InstalledProcess] = []
    lease = _Lease()

    def open_installed_process(*, process_id, expected_executable):
        assert (process_id, expected_executable) == (1234, request.installed_executable)
        process = _InstalledProcess(request)
        installed_processes.append(process)
        return process

    def start_process(arguments, environment, cwd):
        values = list(arguments)
        attempt = launch_attempt_id(values[values.index("--launch-attempt-id") + 1])
        version = values[values.index("--expected-version") + 1]
        StartupHealthReporter(shared_root=request.shared_root, now=lambda: NOW).report(
            transaction_id=request.transaction_id,
            launch_attempt_id=attempt,
            expected_version=version,
            actual_version=version,
            executable_path=values[0],
            healthy=True,
        )
        return SimpleNamespace(pid=4321)

    attempts = iter((launch_attempt_id("attempt-new"), launch_attempt_id("attempt-old")))
    executor = ManagedUpdateHostExecutor(
        manifest_verifier=_Verifier(),
        candidate_builder=_CandidateBuilder(),
        environment={"CLIPAI_INSTANCE_NAME": "managed-e2e"},
        now=lambda: NOW,
        launch_attempt_factory=lambda: next(attempts),
        process_handle_factory=open_installed_process,
        update_gate_factory=lambda _install_root: _FreeGate(lease),
        start_process=start_process,
    )

    assert executor.execute(command) == 0
    result = ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1").read("result")
    assert (result.outcome, result.active_version) == ("updated", "2.0")
    assert read_json(request.install_root / "install-state.json")["current_version"] == "2.0"
    assert (request.install_root / "versions" / "1.0").is_dir()
    assert installed_processes[0].waited is True
    assert installed_processes[0].closed is True
    assert lease.closed is True


def test_host_process_identity_failure_publishes_terminal_result_before_bundle_access(tmp_path: Path):
    command, request = _write_request(tmp_path)

    def reject_process(**_identity):
        raise ManagedProcessIdentityError("wrong executable")

    executor = ManagedUpdateHostExecutor(
        manifest_verifier=_Verifier(),
        candidate_builder=_CandidateBuilder(),
        environment={},
        now=lambda: NOW,
        launch_attempt_factory=lambda: launch_attempt_id("unused-attempt"),
        process_handle_factory=reject_process,
    )

    assert executor.execute(command) == 1
    result = ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1").read("result")
    assert (result.outcome, result.active_version, result.failure_code) == (
        "failed",
        "1.0",
        FailureCode.IDENTITY_INELIGIBLE,
    )
    assert not (request.shared_root / "managed-update" / "transactions" / "tx-1" / "journal.json").exists()


def test_host_busy_publishes_terminal_result_before_opening_installed_process(tmp_path: Path):
    command, request = _write_request(tmp_path)

    def must_not_open_process(**_identity):
        raise AssertionError("busy host must not open the installed process")

    executor = ManagedUpdateHostExecutor(
        manifest_verifier=_Verifier(),
        candidate_builder=_CandidateBuilder(),
        environment={},
        now=lambda: NOW,
        launch_attempt_factory=lambda: launch_attempt_id("unused-attempt"),
        process_handle_factory=must_not_open_process,
        update_gate_factory=lambda _install_root: _BusyGate(),
    )

    assert executor.execute(command) == 1
    result = ManagedUpdateArtifactStore(shared_root=request.shared_root, transaction_id="tx-1").read("result")
    assert (result.outcome, result.active_version, result.failure_code) == (
        "failed",
        "1.0",
        FailureCode.UPDATE_BUSY,
    )
    assert not (request.shared_root / "managed-update" / "transactions" / "tx-1" / "journal.json").exists()
