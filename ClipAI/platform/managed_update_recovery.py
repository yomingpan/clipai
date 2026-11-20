from __future__ import annotations

from pathlib import Path

from ClipAI.core.managed_update import TransactionId, transaction_id
from ClipAI.platform.managed_update_fs import directory_names, native_path, require_contained
from ClipAI.platform.update_artifacts import ManagedUpdateArtifactStore


class IncompleteUpdateError(RuntimeError):
    pass


def find_incomplete_update(shared_root: str | Path) -> TransactionId | None:
    """Find the only durable request+journal transaction without a result."""
    shared = Path(shared_root).resolve()
    transactions_root = require_contained(
        shared,
        shared / "managed-update" / "transactions",
    )
    incomplete: list[TransactionId] = []
    for name in directory_names(transactions_root):
        try:
            tid = transaction_id(name)
            store = ManagedUpdateArtifactStore(shared_root=shared, transaction_id=name)
        except (ValueError, OSError):
            continue
        journal_path = require_contained(
            transactions_root / name,
            transactions_root / name / "journal.json",
        )
        if (
            native_path(store.path("request")).is_file()
            and native_path(journal_path).is_file()
            and not native_path(store.path("result")).is_file()
        ):
            incomplete.append(tid)
    if len(incomplete) > 1:
        raise IncompleteUpdateError("multiple incomplete managed updates require manual recovery")
    return incomplete[0] if incomplete else None
