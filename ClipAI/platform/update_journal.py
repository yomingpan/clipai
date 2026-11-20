from __future__ import annotations

from pathlib import Path

from packaging.version import InvalidVersion, Version

from ClipAI.core.managed_update import FailureCode, TransactionId, TransactionPhase, TransactionSnapshot
from ClipAI.platform.managed_update_fs import ManagedUpdateFileError, atomic_write_json, native_path, read_json, require_contained


JOURNAL_KIND = "clipai-managed-update-journal-v1"
_FIELDS = {
    "schema_version", "journal_kind", "revision", "transaction_id", "phase",
    "installed_version", "target_version", "failure_code",
}
_FORWARD = {
    TransactionPhase.VERIFY: TransactionPhase.PREPARE,
    TransactionPhase.PREPARE: TransactionPhase.SHUTDOWN,
    TransactionPhase.SHUTDOWN: TransactionPhase.COMMIT,
    TransactionPhase.COMMIT: TransactionPhase.LAUNCH,
    TransactionPhase.LAUNCH: TransactionPhase.HEALTH,
    TransactionPhase.HEALTH: TransactionPhase.FINALIZE,
}
_ROLLBACK_SOURCES = {
    TransactionPhase.VERIFY,
    TransactionPhase.PREPARE,
    TransactionPhase.SHUTDOWN,
    TransactionPhase.COMMIT,
    TransactionPhase.LAUNCH,
    TransactionPhase.HEALTH,
    TransactionPhase.FINALIZE,
    TransactionPhase.ROLLBACK,
}


class JournalValidationError(ValueError):
    pass


class JsonUpdateTransactionJournal:
    """Persist the latest pre-side-effect transaction intent as one atomic JSON file."""

    def __init__(self, *, shared_root: str | Path, transaction_id: TransactionId) -> None:
        root = Path(shared_root).resolve()
        self._transaction_id = transaction_id
        self.path = require_contained(
            root,
            root / "managed-update" / "transactions" / str(transaction_id) / "journal.json",
        )

    def record(self, snapshot: TransactionSnapshot) -> None:
        if snapshot.transaction_id != self._transaction_id:
            raise JournalValidationError("journal transaction does not match")
        _version(snapshot.installed_version)
        _version(snapshot.target_version)
        previous = self.read() if native_path(self.path).is_file() else None
        if previous is None:
            if snapshot.phase is not TransactionPhase.VERIFY or snapshot.failure_code is not None:
                raise JournalValidationError("journal must begin at verify")
            revision = 0
        else:
            previous_revision, previous_snapshot = previous
            if (
                snapshot.installed_version != previous_snapshot.installed_version
                or snapshot.target_version != previous_snapshot.target_version
            ):
                raise JournalValidationError("journal version identity changed")
            if not _legal_transition(previous_snapshot.phase, snapshot.phase):
                raise JournalValidationError("journal phase transition is invalid")
            if snapshot.phase is TransactionPhase.ROLLBACK and snapshot.failure_code is None:
                raise JournalValidationError("rollback intent requires a failure code")
            revision = previous_revision + 1
        atomic_write_json(self.path, {
            "schema_version": 1,
            "journal_kind": JOURNAL_KIND,
            "revision": revision,
            "transaction_id": str(snapshot.transaction_id),
            "phase": snapshot.phase.value,
            "installed_version": snapshot.installed_version,
            "target_version": snapshot.target_version,
            "failure_code": snapshot.failure_code.value if snapshot.failure_code else None,
        })

    def read(self) -> tuple[int, TransactionSnapshot]:
        try:
            payload = read_json(self.path)
            if not isinstance(payload, dict) or set(payload) != _FIELDS:
                raise JournalValidationError("journal fields do not match schema")
            if payload["schema_version"] != 1 or payload["journal_kind"] != JOURNAL_KIND:
                raise JournalValidationError("journal identity is unsupported")
            revision = payload["revision"]
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise JournalValidationError("journal revision is invalid")
            if payload["transaction_id"] != self._transaction_id:
                raise JournalValidationError("journal transaction does not match")
            try:
                phase = TransactionPhase(payload["phase"])
                failure = FailureCode(payload["failure_code"]) if payload["failure_code"] is not None else None
            except (TypeError, ValueError) as exc:
                raise JournalValidationError("journal enum value is invalid") from exc
            installed_version = _version(payload["installed_version"])
            target_version = _version(payload["target_version"])
            return revision, TransactionSnapshot(
                self._transaction_id,
                phase,
                installed_version,
                target_version,
                failure,
            )
        except JournalValidationError:
            raise
        except (OSError, ManagedUpdateFileError) as exc:
            raise JournalValidationError("journal is unreadable") from exc


def _legal_transition(previous: TransactionPhase, current: TransactionPhase) -> bool:
    return _FORWARD.get(previous) is current or (current is TransactionPhase.ROLLBACK and previous in _ROLLBACK_SOURCES)


def _version(value: object) -> str:
    if not isinstance(value, str):
        raise JournalValidationError("journal version is invalid")
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise JournalValidationError("journal version is invalid") from exc
    if str(parsed) != value:
        raise JournalValidationError("journal version is not normalized")
    return value
