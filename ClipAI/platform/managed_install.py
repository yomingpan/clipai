from __future__ import annotations

from email.parser import BytesParser
from email.policy import compat32
import os
from pathlib import Path, PurePosixPath
import re
from dataclasses import dataclass
from typing import Protocol

from packaging.version import InvalidVersion, Version

from ClipAI.core.managed_install import ManagedInstallMarker, ManagedInstallState, ManagedUpdateClientIdentity
from ClipAI.core.managed_update import CommitReceipt, FailureCode, ManagedUpdateFailure
from ClipAI.core.update_artifacts import UpdateRequestArtifact
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.managed_update_fs import (
    atomic_write_json,
    canonical_path,
    native_path,
    read_bytes,
    read_json,
    regular_file_inventory,
    require_contained,
)
from ClipAI.platform.update_bundle import parse_install_manifest


MARKER_KIND = "clipai-managed-install-v1"
STATE_KIND = "clipai-managed-install-state-v1"
_MARKER_FIELDS = {
    "schema_version", "marker_kind", "managed_install_id", "install_root",
    "shared_root", "launcher_version", "key_id",
}
_STATE_FIELDS = {
    "schema_version", "state_kind", "managed_install_id", "revision",
    "current_version", "previous_version",
}
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DocumentVerifier(Protocol):
    def verify(self, manifest_path: str | Path, signature_path: str | Path, *, key_id: str) -> None: ...


@dataclass(frozen=True)
class ManagedUpdateClientProof:
    identity: ManagedUpdateClientIdentity
    current: CandidateEnvironment


class ManagedInstallLayout:
    """Own eligibility proof and the single atomic active-version pointer."""

    def __init__(
        self,
        *,
        install_root: str | Path,
        shared_root: str | Path,
        manifest_verifier: DocumentVerifier,
    ) -> None:
        self.install_root = Path(install_root).resolve()
        self.shared_root = Path(shared_root).resolve()
        self._manifest_verifier = manifest_verifier
        self._marker_path = self.install_root / "managed-install.json"
        self._state_path = self.install_root / "install-state.json"

    def assert_update_eligible(self, request: UpdateRequestArtifact) -> ManagedInstallState:
        try:
            marker, state, current = self._current_install_evidence()
            self._assert_request_identity(request, marker, state, current)
            return state
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "managed install identity is not eligible") from exc

    def prove_current_install(self) -> CandidateEnvironment:
        try:
            return self._current_install_evidence()[2]
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.IDENTITY_INELIGIBLE, "managed install selfcheck failed") from exc

    def prove_update_client(
        self,
        *,
        executable_path: str | Path,
        process_id: int,
    ) -> ManagedUpdateClientProof:
        try:
            if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
                raise ValueError("managed process identity is invalid")
            marker, _state, current = self._current_install_evidence()
            if not _same_path(executable_path, current.python):
                raise ValueError("running executable does not match signed current version")
            identity = ManagedUpdateClientIdentity(
                installed_version=current.version,
                launcher_version=marker.launcher_version,
                installed_executable=canonical_path(executable_path),
                installed_process_id=process_id,
                install_root=self.install_root,
                shared_root=self.shared_root,
                managed_install_id=marker.managed_install_id,
            )
            return ManagedUpdateClientProof(identity, current)
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(
                FailureCode.IDENTITY_INELIGIBLE,
                "managed runtime identity is not update eligible",
            ) from exc

    def restore_known_good(self, request: UpdateRequestArtifact) -> CandidateEnvironment:
        """Idempotently restore the request's signed installed version."""
        try:
            marker = _parse_marker(read_json(self._marker_path))
            state = self.read_state()
            self._assert_layout_identity(marker, state)
            if (
                request.managed_install_id != marker.managed_install_id
                or not _same_path(request.install_root, self.install_root)
                or not _same_path(request.shared_root, self.shared_root)
            ):
                raise ValueError("recovery request identity does not match install")
            known_good = self._prove_version(request.installed_version)
            if not _same_path(request.installed_executable, known_good.python):
                raise ValueError("recovery executable does not match known-good version")
            if state.current_version == request.installed_version:
                return known_good
            if (
                state.current_version != request.target_version
                or state.previous_version != request.installed_version
            ):
                raise ValueError("recovery pointer is not old or committed target")
            self._write_state(ManagedInstallState(
                managed_install_id=state.managed_install_id,
                revision=state.revision + 1,
                current_version=request.installed_version,
                previous_version=request.target_version,
            ))
            return known_good
        except ManagedUpdateFailure:
            raise
        except Exception as exc:
            raise ManagedUpdateFailure(FailureCode.ROLLBACK_FAILED, "unable to restore signed known-good version") from exc

    def read_state(self) -> ManagedInstallState:
        return _parse_state(read_json(self._state_path))

    def version_root(self, version: str) -> Path:
        normalized = _version(version)
        return require_contained(self.install_root / "versions", self.install_root / "versions" / normalized)

    def commit(self, candidate: CandidateEnvironment) -> CommitReceipt:
        try:
            state = self.read_state()
            candidate_root = self.version_root(candidate.version)
            if not _same_path(candidate.root, candidate_root):
                raise ValueError("candidate root does not match managed version root")
            previous_root = self.version_root(state.current_version)
            self._write_state(ManagedInstallState(
                managed_install_id=state.managed_install_id,
                revision=state.revision + 1,
                current_version=candidate.version,
                previous_version=state.current_version,
            ))
            return CommitReceipt(previous_root=previous_root, candidate_root=candidate_root)
        except Exception as exc:
            if isinstance(exc, ManagedUpdateFailure):
                raise
            raise ManagedUpdateFailure(FailureCode.COMMIT_FAILED, "unable to commit managed install pointer") from exc

    def rollback(self, receipt: CommitReceipt) -> None:
        try:
            state = self.read_state()
            if not _same_path(self.version_root(state.current_version), receipt.candidate_root):
                raise ValueError("active version no longer matches commit receipt")
            if state.previous_version is None or not _same_path(self.version_root(state.previous_version), receipt.previous_root):
                raise ValueError("previous version no longer matches commit receipt")
            self._write_state(ManagedInstallState(
                managed_install_id=state.managed_install_id,
                revision=state.revision + 1,
                current_version=state.previous_version,
                previous_version=state.current_version,
            ))
        except Exception as exc:
            if isinstance(exc, ManagedUpdateFailure):
                raise
            raise ManagedUpdateFailure(FailureCode.ROLLBACK_FAILED, "unable to restore managed install pointer") from exc

    def finalize(self, receipt: CommitReceipt) -> None:
        state = self.read_state()
        if not _same_path(self.version_root(state.current_version), receipt.candidate_root):
            raise ManagedUpdateFailure(FailureCode.COMMIT_FAILED, "finalized version is no longer active")
        # Deliberately retain receipt.previous_root. A later retention policy may
        # remove it only after the new launch has independently proven healthy.

    def _assert_request_identity(
        self,
        request: UpdateRequestArtifact,
        marker: ManagedInstallMarker,
        state: ManagedInstallState,
        current: CandidateEnvironment,
    ) -> None:
        if not _same_path(request.install_root, self.install_root):
            raise ValueError("install root does not match")
        if not _same_path(request.shared_root, self.shared_root):
            raise ValueError("shared root does not match")
        if request.managed_install_id != marker.managed_install_id:
            raise ValueError("managed install identity does not match")
        if request.installed_version != state.current_version:
            raise ValueError("installed version is stale")
        if not _same_path(request.installed_executable, current.python):
            raise ValueError("running executable is not the managed environment")

    def _current_install_evidence(
        self,
    ) -> tuple[ManagedInstallMarker, ManagedInstallState, CandidateEnvironment]:
        marker = _parse_marker(read_json(self._marker_path))
        state = self.read_state()
        self._assert_layout_identity(marker, state)
        return marker, state, self._prove_version(state.current_version)

    def _assert_layout_identity(
        self,
        marker: ManagedInstallMarker,
        state: ManagedInstallState,
    ) -> None:
        if not _same_path(marker.install_root, self.install_root):
            raise ValueError("install root does not match")
        if not _same_path(marker.shared_root, self.shared_root):
            raise ValueError("shared root does not match")
        if _paths_overlap(self.install_root, self.shared_root):
            raise ValueError("install and shared roots must be disjoint")
        if state.managed_install_id != marker.managed_install_id:
            raise ValueError("managed install identity does not match")

    def _prove_version(self, version: str) -> CandidateEnvironment:
        current_root = self.version_root(version)
        if native_path(current_root / ".git").exists():
            raise ValueError("source checkout is not update eligible")
        expected_python = current_root / ".venv" / "Scripts" / "python.exe"
        if not native_path(expected_python).is_file():
            raise ValueError("managed environment Python is missing")

        manifest_path = current_root / "install-manifest.json"
        manifest = parse_install_manifest(read_json(manifest_path))
        if manifest.app_version != version:
            raise ValueError("installed manifest identity does not match")
        self._manifest_verifier.verify(
            manifest_path,
            manifest_path.with_suffix(".json.sig"),
            key_id=manifest.key_id,
        )
        entrypoint = current_root.joinpath(*PurePosixPath(manifest.entrypoint).parts)
        if not native_path(entrypoint).is_file():
            raise ValueError("managed entrypoint is missing")
        if self._installed_distribution_version(current_root) != version:
            raise ValueError("installed distribution version does not match")
        self._reject_editable_install(current_root)
        return CandidateEnvironment(
            root=current_root,
            python=expected_python,
            entrypoint=entrypoint,
            version=version,
        )

    def _installed_distribution_version(self, current_root: Path) -> str:
        site_packages = current_root / ".venv" / "Lib" / "site-packages"
        metadata_paths = []
        for relative in regular_file_inventory(site_packages):
            parts = PurePosixPath(relative).parts
            if len(parts) == 2 and parts[0].casefold().startswith("clipai-") and parts[0].casefold().endswith(".dist-info") and parts[1] == "METADATA":
                metadata_paths.append(site_packages.joinpath(*parts))
        if len(metadata_paths) != 1:
            raise ValueError("managed distribution metadata is missing or ambiguous")
        metadata = BytesParser(policy=compat32).parsebytes(read_bytes(metadata_paths[0], maximum_size=1024 * 1024))
        if metadata.get("Name", "").casefold() != "clipai":
            raise ValueError("managed distribution name does not match")
        return _version(metadata.get("Version"))

    def _reject_editable_install(self, current_root: Path) -> None:
        site_packages = current_root / ".venv" / "Lib" / "site-packages"
        for relative in regular_file_inventory(site_packages):
            parts = PurePosixPath(relative).parts
            if len(parts) != 2 or not parts[0].casefold().startswith("clipai-") or not parts[0].casefold().endswith(".dist-info") or parts[1] != "direct_url.json":
                continue
            payload = read_json(site_packages.joinpath(*parts))
            if isinstance(payload, dict) and isinstance(payload.get("dir_info"), dict) and payload["dir_info"].get("editable") is True:
                raise ValueError("editable install is not update eligible")

    def _write_state(self, state: ManagedInstallState) -> None:
        atomic_write_json(self._state_path, {
            "schema_version": 1,
            "state_kind": STATE_KIND,
            "managed_install_id": state.managed_install_id,
            "revision": state.revision,
            "current_version": state.current_version,
            "previous_version": state.previous_version,
        })


def read_stable_launcher_marker(application_root: str | Path) -> ManagedInstallMarker | None:
    """Return verified local layout identity only for the fixed launcher root."""
    launcher_root = canonical_path(application_root)
    if launcher_root.name.casefold() != "launcher":
        return None
    marker_path = launcher_root.parent / "managed-install.json"
    if not native_path(marker_path).is_file():
        return None
    marker = _parse_marker(read_json(marker_path))
    if not _same_path(marker.install_root, launcher_root.parent):
        raise ValueError("stable launcher marker install root does not match")
    return marker


def _parse_marker(value: object) -> ManagedInstallMarker:
    data = _mapping(value, _MARKER_FIELDS, "managed install marker")
    if data["schema_version"] != 1 or data["marker_kind"] != MARKER_KIND:
        raise ValueError("managed install marker identity is unsupported")
    return ManagedInstallMarker(
        managed_install_id=_identity(data["managed_install_id"], "managed_install_id"),
        install_root=_absolute(data["install_root"]),
        shared_root=_absolute(data["shared_root"]),
        launcher_version=_version(data["launcher_version"]),
        key_id=_identity(data["key_id"], "key_id"),
    )


def _parse_state(value: object) -> ManagedInstallState:
    data = _mapping(value, _STATE_FIELDS, "managed install state")
    if data["schema_version"] != 1 or data["state_kind"] != STATE_KIND:
        raise ValueError("managed install state identity is unsupported")
    revision = data["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("install state revision is invalid")
    previous = data["previous_version"]
    if previous is not None:
        previous = _version(previous)
    return ManagedInstallState(
        managed_install_id=_identity(data["managed_install_id"], "managed_install_id"),
        revision=revision,
        current_version=_version(data["current_version"]),
        previous_version=previous,
    )


def _mapping(value: object, fields: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} fields do not match schema")
    return value


def _identity(value: object, name: str) -> str:
    if not isinstance(value, str) or _IDENTITY.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")
    return value


def _absolute(value: object) -> Path:
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError("managed install path must be absolute")
    return Path(value)


def _version(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("managed install version is invalid")
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise ValueError("managed install version is invalid") from exc
    if str(parsed) != value:
        raise ValueError("managed install version is not normalized")
    return value


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def _paths_overlap(left: Path, right: Path) -> bool:
    return _same_path(left, right) or left.is_relative_to(right) or right.is_relative_to(left)
