from pathlib import Path

import pytest

from ClipAI.core.managed_update import TransactionPhase, TransactionSnapshot, transaction_id
from ClipAI.core.update_artifacts import UpdateRequestArtifact, UpdateResultArtifact
from ClipAI.platform.managed_update_recovery import IncompleteUpdateError, find_incomplete_update
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore
from ClipAI.platform.update_journal import JsonUpdateTransactionJournal


NOW = "2026-09-13T00:00:00+00:00"


def _write_incomplete(shared_root: Path, name: str) -> None:
    tid = transaction_id(name)
    install_root = (shared_root.parent / f"install-{name}").resolve()
    request = UpdateRequestArtifact(
        tid, NOW, "1.0", "2.0",
        install_root / "versions" / "1.0" / ".venv" / "Scripts" / "python.exe",
        123, shared_root / "bundle.zip", 42, "a" * 64, "b" * 64,
        "release-key", install_root, shared_root, f"managed-{name}",
    )
    ManagedUpdateArtifactStore(shared_root=shared_root, transaction_id=name).write(request)
    JsonUpdateTransactionJournal(shared_root=shared_root, transaction_id=tid).record(
        TransactionSnapshot(tid, TransactionPhase.VERIFY, "1.0", "2.0")
    )


def test_scanner_returns_only_request_journal_pair_without_terminal_result(tmp_path: Path):
    shared_root = (tmp_path / "shared").resolve()
    _write_incomplete(shared_root, "tx-active")
    _write_incomplete(shared_root, "tx-done")
    ManagedUpdateArtifactStore(shared_root=shared_root, transaction_id="tx-done").write(
        UpdateResultArtifact(transaction_id("tx-done"), NOW, "rolled_back", "1.0")
    )

    assert find_incomplete_update(shared_root) == transaction_id("tx-active")


def test_scanner_fails_closed_for_multiple_incomplete_transactions(tmp_path: Path):
    shared_root = (tmp_path / "shared").resolve()
    _write_incomplete(shared_root, "tx-one")
    _write_incomplete(shared_root, "tx-two")

    with pytest.raises(IncompleteUpdateError, match="multiple"):
        find_incomplete_update(shared_root)


def test_scanner_ignores_unrelated_and_partial_directories(tmp_path: Path):
    shared_root = (tmp_path / "shared").resolve()
    partial = shared_root / "managed-update" / "transactions" / "partial"
    partial.mkdir(parents=True)
    (partial / "note.txt").write_text("unrelated", encoding="utf-8")

    assert find_incomplete_update(shared_root) is None
