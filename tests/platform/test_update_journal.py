from pathlib import Path

import pytest

from ClipAI.core.managed_update import FailureCode, TransactionPhase, TransactionSnapshot, transaction_id
from ClipAI.platform.managed_update_fs import atomic_write_json, read_json
from ClipAI.platform.update_journal import JournalValidationError, JsonUpdateTransactionJournal


def _snapshot(phase: TransactionPhase, failure: FailureCode | None = None) -> TransactionSnapshot:
    return TransactionSnapshot(transaction_id("tx-1"), phase, "1.0", "2.0", failure)


def test_journal_atomically_records_monotonic_pre_side_effect_intent(tmp_path: Path):
    journal = JsonUpdateTransactionJournal(shared_root=tmp_path, transaction_id=transaction_id("tx-1"))
    journal.record(_snapshot(TransactionPhase.VERIFY))
    journal.record(_snapshot(TransactionPhase.PREPARE))
    journal.record(_snapshot(TransactionPhase.SHUTDOWN))
    journal.record(_snapshot(TransactionPhase.COMMIT))
    journal.record(_snapshot(TransactionPhase.ROLLBACK, FailureCode.COMMIT_FAILED))

    revision, snapshot = journal.read()
    assert revision == 4
    assert snapshot.phase is TransactionPhase.ROLLBACK
    assert snapshot.failure_code is FailureCode.COMMIT_FAILED
    assert read_json(journal.path)["journal_kind"] == "clipai-managed-update-journal-v1"


def test_journal_rejects_skips_identity_changes_and_rollback_without_failure(tmp_path: Path):
    journal = JsonUpdateTransactionJournal(shared_root=tmp_path, transaction_id=transaction_id("tx-1"))
    with pytest.raises(JournalValidationError, match="begin"):
        journal.record(_snapshot(TransactionPhase.PREPARE))
    journal.record(_snapshot(TransactionPhase.VERIFY))
    with pytest.raises(JournalValidationError, match="transition"):
        journal.record(_snapshot(TransactionPhase.COMMIT))
    journal.record(_snapshot(TransactionPhase.PREPARE))
    journal.record(_snapshot(TransactionPhase.SHUTDOWN))
    journal.record(_snapshot(TransactionPhase.COMMIT))
    with pytest.raises(JournalValidationError, match="failure"):
        journal.record(_snapshot(TransactionPhase.ROLLBACK))
    changed = TransactionSnapshot(transaction_id("tx-1"), TransactionPhase.LAUNCH, "1.1", "2.0")
    with pytest.raises(JournalValidationError, match="version"):
        journal.record(changed)


def test_journal_fails_closed_on_unknown_or_wrong_transaction_schema(tmp_path: Path):
    journal = JsonUpdateTransactionJournal(shared_root=tmp_path, transaction_id=transaction_id("tx-1"))
    journal.record(_snapshot(TransactionPhase.VERIFY))
    payload = read_json(journal.path)
    payload["extra"] = True
    atomic_write_json(journal.path, payload)
    with pytest.raises(JournalValidationError, match="fields"):
        journal.read()

    other = JsonUpdateTransactionJournal(shared_root=tmp_path, transaction_id=transaction_id("tx-2"))
    atomic_write_json(other.path, {key: value for key, value in payload.items() if key != "extra"})
    with pytest.raises(JournalValidationError, match="transaction"):
        other.read()


@pytest.mark.parametrize("interrupted_phase", list(TransactionPhase))
def test_recovery_rollback_is_legal_from_every_incomplete_phase_and_is_reentrant(
    tmp_path: Path,
    interrupted_phase: TransactionPhase,
) -> None:
    journal = JsonUpdateTransactionJournal(shared_root=tmp_path, transaction_id=transaction_id("tx-1"))
    forward = (
        TransactionPhase.VERIFY,
        TransactionPhase.PREPARE,
        TransactionPhase.SHUTDOWN,
        TransactionPhase.COMMIT,
        TransactionPhase.LAUNCH,
        TransactionPhase.HEALTH,
        TransactionPhase.FINALIZE,
    )
    stop = TransactionPhase.HEALTH if interrupted_phase is TransactionPhase.ROLLBACK else interrupted_phase
    for phase in forward[:forward.index(stop) + 1]:
        journal.record(_snapshot(phase))
    journal.record(_snapshot(TransactionPhase.ROLLBACK, FailureCode.UPDATE_INTERRUPTED))
    journal.record(_snapshot(TransactionPhase.ROLLBACK, FailureCode.UPDATE_INTERRUPTED))

    revision, snapshot = journal.read()
    assert revision >= 2
    assert snapshot.phase is TransactionPhase.ROLLBACK
    assert snapshot.failure_code is FailureCode.UPDATE_INTERRUPTED
