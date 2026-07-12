from __future__ import annotations

import time
from collections.abc import Callable

from ClipAI.core.ports import ArchiveStore, ClipboardTransactionStore, KeyboardOutput
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator


class OutputActions:
    def __init__(
        self,
        *,
        clipboard: ClipboardTransactionStore,
        archive: ArchiveStore | None = None,
        keyboard: KeyboardOutput | None = None,
        paste_restore_delay_sec: float = 0.25,
        wait: Callable[[float], None] = time.sleep,
        clipboard_transactions: ClipboardTransactionCoordinator | None = None,
    ) -> None:
        self._clipboard = clipboard
        self._archive = archive
        self._keyboard = keyboard
        self._paste_restore_delay_sec = paste_restore_delay_sec
        self._wait = wait
        self._clipboard_transactions = clipboard_transactions or ClipboardTransactionCoordinator(clipboard)

    def copy(self, text: str) -> None:
        self._clipboard.write_text(text)

    def archive(self, text: str) -> None:
        if self._archive is None:
            raise RuntimeError("archive output is not configured")
        self._archive.save(text)

    @property
    def can_archive(self) -> bool:
        return self._archive is not None

    def paste(self, text: str) -> None:
        if self._keyboard is None:
            raise RuntimeError("keyboard output is not configured")
        with self._clipboard_transactions.temporary_text(text):
            self._keyboard.paste()
            self._wait(self._paste_restore_delay_sec)

    @property
    def can_paste(self) -> bool:
        return self._keyboard is not None
