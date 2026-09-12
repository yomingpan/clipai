from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from ClipAI.core.managed_update import FailureCode, transaction_id, launch_attempt_id
from ClipAI.core.update_artifacts import (
    HandoffReadyArtifact,
    LaunchReceiptArtifact,
    StartupHealthArtifact,
    UpdateArtifact,
    UpdateRequestArtifact,
    UpdateResultArtifact,
)
from ClipAI.platform.managed_update_fs import atomic_write_json, read_json


_COMMON = {"schema_version", "artifact_kind", "transaction_id", "created_at"}
_FIELDS = {
    "request": _COMMON | {"installed_version", "target_version", "bundle_path", "install_root", "shared_root", "managed_install_id"},
    "handoff_ready": _COMMON | {"candidate_root", "candidate_python", "manifest_sha256", "expected_version"},
    "launch_receipt": _COMMON | {"launch_attempt_id", "expected_version", "executable_path", "process_id"},
    "startup_health": _COMMON | {"launch_attempt_id", "expected_version", "actual_version", "executable_path", "healthy"},
    "result": _COMMON | {"outcome", "active_version", "failure_code", "rollback_failure_code"},
}
_KINDS = {
    UpdateRequestArtifact: "request",
    HandoffReadyArtifact: "handoff_ready",
    LaunchReceiptArtifact: "launch_receipt",
    StartupHealthArtifact: "startup_health",
    UpdateResultArtifact: "result",
}


class ArtifactValidationError(ValueError):
    pass


def write_artifact(path: str | Path, artifact: UpdateArtifact) -> None:
    kind = _KINDS[type(artifact)]
    payload = asdict(artifact)
    payload.update(schema_version=1, artifact_kind=kind)
    atomic_write_json(path, _json_values(payload))


def read_artifact(
    path: str | Path,
    *,
    expected_kind: str,
    expected_transaction_id: str | None = None,
) -> UpdateArtifact:
    payload = read_json(path)
    if not isinstance(payload, dict) or expected_kind not in _FIELDS or set(payload) != _FIELDS[expected_kind]:
        raise ArtifactValidationError("artifact fields do not match schema")
    if payload["schema_version"] != 1 or payload["artifact_kind"] != expected_kind:
        raise ArtifactValidationError("artifact identity does not match")
    tid = _identity(payload["transaction_id"], transaction_id, "transaction_id")
    if expected_transaction_id is not None and tid != expected_transaction_id:
        raise ArtifactValidationError("artifact transaction does not match")
    created_at = _timestamp(payload["created_at"])
    if expected_kind == "request":
        return UpdateRequestArtifact(
            tid, created_at, _version(payload["installed_version"]), _version(payload["target_version"]),
            _absolute(payload["bundle_path"]), _absolute(payload["install_root"]), _absolute(payload["shared_root"]),
            _text(payload["managed_install_id"], "managed_install_id"),
        )
    if expected_kind == "handoff_ready":
        return HandoffReadyArtifact(
            tid, created_at, _absolute(payload["candidate_root"]), _absolute(payload["candidate_python"]),
            _sha256(payload["manifest_sha256"]), _version(payload["expected_version"]),
        )
    if expected_kind == "launch_receipt":
        process_id = payload["process_id"]
        if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
            raise ArtifactValidationError("process_id must be positive")
        return LaunchReceiptArtifact(
            tid, created_at, _identity(payload["launch_attempt_id"], launch_attempt_id, "launch_attempt_id"),
            _version(payload["expected_version"]), _absolute(payload["executable_path"]), process_id,
        )
    if expected_kind == "startup_health":
        healthy = payload["healthy"]
        if not isinstance(healthy, bool):
            raise ArtifactValidationError("healthy must be boolean")
        return StartupHealthArtifact(
            tid, created_at, _identity(payload["launch_attempt_id"], launch_attempt_id, "launch_attempt_id"),
            _version(payload["expected_version"]), _version(payload["actual_version"]),
            _absolute(payload["executable_path"]), healthy,
        )
    outcome = payload["outcome"]
    if outcome not in {"updated", "rolled_back", "failed"}:
        raise ArtifactValidationError("result outcome is invalid")
    return UpdateResultArtifact(
        tid, created_at, outcome, _version(payload["active_version"]),
        _failure(payload["failure_code"]), _failure(payload["rollback_failure_code"]),
    )


def validate_health_relation(
    launch: LaunchReceiptArtifact,
    health: StartupHealthArtifact,
) -> None:
    if (
        launch.transaction_id != health.transaction_id
        or launch.launch_attempt_id != health.launch_attempt_id
        or launch.expected_version != health.expected_version
        or health.actual_version != launch.expected_version
        or launch.executable_path.resolve() != health.executable_path.resolve()
        or not health.healthy
    ):
        raise ArtifactValidationError("startup health does not match launch")


def _json_values(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, FailureCode):
        return value.value
    if isinstance(value, dict):
        return {key: _json_values(item) for key, item in value.items()}
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactValidationError(f"{name} must be a canonical string")
    return value


def _identity(value: object, parser: object, name: str):
    text = _text(value, name)
    try:
        return parser(text)  # type: ignore[operator]
    except ValueError as exc:
        raise ArtifactValidationError(f"{name} is invalid") from exc


def _version(value: object) -> str:
    text = _text(value, "version")
    try:
        version = Version(text)
    except InvalidVersion as exc:
        raise ArtifactValidationError("version is invalid") from exc
    if str(version) != text:
        raise ArtifactValidationError("version is not normalized")
    return text


def _absolute(value: object) -> Path:
    path = Path(_text(value, "path"))
    if not path.is_absolute():
        raise ArtifactValidationError("artifact path must be absolute")
    return path


def _timestamp(value: object) -> str:
    text = _text(value, "created_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactValidationError("created_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ArtifactValidationError("created_at must include timezone")
    return text


def _sha256(value: object) -> str:
    text = _text(value, "sha256")
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ArtifactValidationError("sha256 is invalid")
    return text


def _failure(value: object) -> FailureCode | None:
    if value is None:
        return None
    try:
        return FailureCode(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError("failure code is invalid") from exc
