from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import logging
import threading
import time
from typing import Generic, TypeVar
import uuid

from ClipAI.core.errors import PASTE_FAILURE_MESSAGES, PasteFailure
from ClipAI.core.models import PasteCleanupState, SelectionCaptureOutcome
from ClipAI.core.ports import ClipboardTransactionStore, SelectionCaptureAdapter
from ClipAI.core.state import CancellationToken


SnapshotT = TypeVar("SnapshotT")
ResultT = TypeVar("ResultT")
_MODIFIER_KEYS = ("ctrl", "alt", "shift")
logger = logging.getLogger("clipai.clipboard_transaction")


@dataclass(frozen=True)
class TemporaryTextResult(Generic[ResultT]):
    value: ResultT | None = None
    error: Exception | None = None
    cancelled: bool = False
    cleanup: PasteCleanupState = "not_required"


class ClipboardTransactionCoordinator(Generic[SnapshotT]):
    """The sole owner of temporary clipboard mutation and conditional restore."""

    def __init__(self, clipboard: ClipboardTransactionStore[SnapshotT]) -> None:
        self._clipboard = clipboard
        self._lock = threading.Lock()
        self._active_operation_id: str | None = None

    def use_temporary_text(
        self,
        operation_id: str,
        text: str,
        work: Callable[[], ResultT],
        cancellation: CancellationToken | None = None,
    ) -> TemporaryTextResult[ResultT]:
        """Run work while transient text is owned, preserving lifecycle truth."""

        with self._transaction(operation_id):
            if self._cancelled(cancellation):
                logger.info(
                    "Clipboard transaction trace stage=cancelled operation_id=%s checkpoint=before_snapshot",
                    operation_id,
                )
                return TemporaryTextResult(cancelled=True)
            try:
                if self._clipboard.sequence_number() <= 0:
                    raise OSError("Clipboard sequence tracking is unavailable.")
                original = self._clipboard.snapshot()
            except Exception as exc:
                logger.warning(
                    "Clipboard transaction trace stage=snapshot_failed operation_id=%s error_type=%s",
                    operation_id,
                    type(exc).__name__,
                )
                return TemporaryTextResult(error=_clipboard_failure(exc))
            logger.info(
                "Clipboard transaction trace stage=snapshot_complete operation_id=%s",
                operation_id,
            )
            if self._cancelled(cancellation):
                logger.info(
                    "Clipboard transaction trace stage=cancelled operation_id=%s checkpoint=after_snapshot",
                    operation_id,
                )
                return TemporaryTextResult(cancelled=True)

            try:
                self._clipboard.write_transient_text(text)
                owned_sequence = self._clipboard.sequence_number()
                if owned_sequence <= 0:
                    raise OSError("Clipboard sequence tracking was lost after mutation.")
            except Exception as exc:
                logger.warning(
                    "Clipboard transaction trace stage=transient_write_failed operation_id=%s error_type=%s",
                    operation_id,
                    type(exc).__name__,
                )
                return TemporaryTextResult(
                    error=_clipboard_failure(exc),
                    cleanup="failed",
                )
            logger.info(
                "Clipboard transaction trace stage=transient_written operation_id=%s owned_sequence=%s",
                operation_id,
                owned_sequence,
            )

            value: ResultT | None = None
            error: Exception | None = None
            cancelled = False
            try:
                if self._cancelled(cancellation):
                    cancelled = True
                else:
                    logger.info(
                        "Clipboard transaction trace stage=work_started operation_id=%s",
                        operation_id,
                    )
                    value = work()
                    logger.info(
                        "Clipboard transaction trace stage=work_returned operation_id=%s result_type=%s",
                        operation_id,
                        type(value).__name__,
                    )
            except Exception as exc:
                error = exc
                logger.warning(
                    "Clipboard transaction trace stage=work_error operation_id=%s error_type=%s",
                    operation_id,
                    type(exc).__name__,
                )

            cleanup: PasteCleanupState = "restored"
            try:
                if not self._clipboard.restore_if_unchanged(original, owned_sequence):
                    cleanup = "external_change"
            except Exception as exc:
                cleanup = "failed"
                if error is None:
                    error = _clipboard_failure(exc)
            logger.info(
                "Clipboard transaction trace stage=cleanup operation_id=%s state=%s owned_sequence=%s",
                operation_id,
                cleanup,
                owned_sequence,
            )

            return TemporaryTextResult(
                value=value,
                error=error,
                cancelled=cancelled,
                cleanup=cleanup,
            )

    def write_text(self, text: str) -> None:
        """Serialize durable clipboard writes with temporary Paste ownership."""

        with self._transaction("clipboard-write"):
            self._clipboard.write_text(text)

    def capture_selection(
        self,
        operation_id: str,
        adapter: SelectionCaptureAdapter,
        *,
        cancellation: CancellationToken | None = None,
        modifier_release_timeout_sec: float = 1.0,
        timeout_sec: float = 0.35,
        poll_sec: float = 0.02,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> SelectionCaptureOutcome:
        with self._transaction(operation_id):
            modifier_deadline = monotonic() + modifier_release_timeout_sec
            while any(adapter.modifier_is_pressed(key) is True for key in _MODIFIER_KEYS):
                if self._cancelled(cancellation):
                    return SelectionCaptureOutcome(status="cancelled")
                if monotonic() >= modifier_deadline:
                    return SelectionCaptureOutcome(status="modifier_timeout")
                wait(poll_sec)

            try:
                original = self._clipboard.snapshot()
            except Exception:
                return SelectionCaptureOutcome(status="failed")
            marker = f"__CLIPAI_SELECTION_{uuid.uuid4().hex}__"
            owned_sequence: int | None = None
            try:
                self._clipboard.write_transient_text(marker)
                owned_sequence = self._clipboard.sequence_number()
                adapter.copy_selection()
                deadline = monotonic() + timeout_sec
                while monotonic() < deadline:
                    if self._cancelled(cancellation):
                        return SelectionCaptureOutcome(status="cancelled")
                    value = self._clipboard.read_text()
                    if value != marker:
                        candidate_sequence = self._clipboard.sequence_number()
                        confirmed = self._clipboard.read_text()
                        if confirmed == value and self._clipboard.sequence_number() == candidate_sequence:
                            owned_sequence = candidate_sequence
                            text = value.strip()
                            return SelectionCaptureOutcome(text, "captured" if text else "empty")
                        owned_sequence = None
                        return SelectionCaptureOutcome(status="failed")
                    wait(poll_sec)
                return SelectionCaptureOutcome(status="empty")
            except Exception:
                return SelectionCaptureOutcome(status="failed")
            finally:
                if owned_sequence is not None:
                    try:
                        self._clipboard.restore_if_unchanged(original, owned_sequence)
                    except Exception:
                        pass

    @contextmanager
    def _transaction(self, operation_id: str) -> Iterator[None]:
        with self._lock:
            if self._active_operation_id is not None:
                raise RuntimeError("clipboard transaction ownership was not released")
            self._active_operation_id = operation_id
            try:
                yield
            finally:
                self._active_operation_id = None

    @staticmethod
    def _cancelled(cancellation: CancellationToken | None) -> bool:
        return cancellation is not None and cancellation.is_cancelled

    @classmethod
    def _raise_if_cancelled(cls, cancellation: CancellationToken | None) -> None:
        if cls._cancelled(cancellation):
            raise RuntimeError("clipboard transaction was cancelled")


def _clipboard_failure(error: Exception) -> PasteFailure:
    if isinstance(error, PasteFailure):
        return error
    return PasteFailure(
        "clipboard_unavailable",
        PASTE_FAILURE_MESSAGES["clipboard_unavailable"],
    )
