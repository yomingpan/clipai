from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

from ClipAI.core.managed_update import launch_attempt_id, transaction_id
from ClipAI.core.update_artifacts import LaunchReceiptArtifact, StartupHealthArtifact, UpdateRequestArtifact
from ClipAI.platform.managed_update_fs import atomic_write_json
from ClipAI.platform.update_artifacts import ArtifactValidationError, ManagedUpdateArtifactStore, read_artifact, validate_health_relation, write_artifact


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc).isoformat()


def test_request_artifact_round_trips_with_exact_transaction(tmp_path: Path):
    artifact = UpdateRequestArtifact(transaction_id("tx-1"), NOW, "3.7.3", "3.8.0", (tmp_path / "python.exe").resolve(), 1234, (tmp_path / "b.zip").resolve(), 42, "a" * 64, "b" * 64, "release-key", (tmp_path / "install").resolve(), (tmp_path / "shared").resolve(), "managed-1")
    path = tmp_path / "request.json"
    write_artifact(path, artifact)
    assert read_artifact(path, expected_kind="request", expected_transaction_id="tx-1") == artifact
    with pytest.raises(ArtifactValidationError, match="transaction"):
        read_artifact(path, expected_kind="request", expected_transaction_id="tx-2")


def test_launch_health_relation_requires_attempt_version_executable_and_health(tmp_path: Path):
    executable = (tmp_path / "versions" / "3.8.0" / ".venv" / "python.exe").resolve()
    launch = LaunchReceiptArtifact(transaction_id("tx-1"), NOW, launch_attempt_id("a-1"), "3.8.0", executable, 42)
    health = StartupHealthArtifact(transaction_id("tx-1"), NOW, launch_attempt_id("a-1"), "3.8.0", "3.8.0", executable, True)
    validate_health_relation(launch, health)
    with pytest.raises(ArtifactValidationError, match="does not match"):
        validate_health_relation(launch, StartupHealthArtifact(health.transaction_id, NOW, launch_attempt_id("a-2"), "3.8.0", "3.8.0", executable, True))


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length identity")
def test_artifact_reader_canonicalizes_extended_length_executable(tmp_path: Path):
    executable = (tmp_path / "versions" / "3.8.0" / ".venv" / "python.exe").resolve()
    launch = LaunchReceiptArtifact(
        transaction_id("tx-1"), NOW, launch_attempt_id("a-1"), "3.8.0", executable, 42,
    )
    health_path = tmp_path / "startup-health.json"
    write_artifact(
        health_path,
        StartupHealthArtifact(
            transaction_id("tx-1"),
            NOW,
            launch_attempt_id("a-1"),
            "3.8.0",
            "3.8.0",
            Path("\\\\?\\" + str(executable)),
            True,
        ),
    )

    health = read_artifact(
        health_path,
        expected_kind="startup_health",
        expected_transaction_id="tx-1",
    )

    assert isinstance(health, StartupHealthArtifact)
    assert health.executable_path == executable
    validate_health_relation(launch, health)


def test_artifacts_reject_unknown_fields_and_relative_paths(tmp_path: Path):
    path = tmp_path / "request.json"
    atomic_write_json(path, {"schema_version": 1, "artifact_kind": "request", "transaction_id": "tx", "created_at": NOW, "installed_version": "3.7.3", "target_version": "3.8.0", "installed_executable": str((tmp_path / "python.exe").resolve()), "installed_process_id": 1234, "bundle_path": "relative.zip", "bundle_size": 42, "bundle_sha256": "a" * 64, "manifest_sha256": "b" * 64, "key_id": "key", "install_root": str(tmp_path.resolve()), "shared_root": str(tmp_path.resolve()), "managed_install_id": "id", "extra": True})
    with pytest.raises(ArtifactValidationError, match="fields"):
        read_artifact(path, expected_kind="request")


def test_artifact_store_contains_kind_paths_under_exact_transaction(tmp_path: Path):
    artifact = UpdateRequestArtifact(transaction_id("tx-1"), NOW, "3.7.3", "3.8.0", (tmp_path / "python.exe").resolve(), 1234, (tmp_path / "b.zip").resolve(), 42, "a" * 64, "b" * 64, "release-key", (tmp_path / "install").resolve(), (tmp_path / "shared").resolve(), "managed-1")
    store = ManagedUpdateArtifactStore(shared_root=tmp_path, transaction_id="tx-1")
    path = store.write(artifact)
    assert path == tmp_path / "managed-update" / "transactions" / "tx-1" / "request.json"
    assert store.read("request") == artifact
    with pytest.raises(ArtifactValidationError, match="transaction"):
        ManagedUpdateArtifactStore(shared_root=tmp_path, transaction_id="tx-2").write(artifact)
