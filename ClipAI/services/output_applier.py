from __future__ import annotations

import logging
import time

from clipai.context.clipboard_session import ClipboardSession
from clipai.output import maybe_auto_paste
from clipai.platform.clipboard import write_clipboard_text

logger = logging.getLogger("clipai.output")
PASTE_RESTORE_DELAY_SEC = 0.35


class OutputModeError(RuntimeError):
    pass


class OutputApplier:
    def apply(self, content: str, output_mode: str) -> None:
        normalized_mode = (output_mode or "stdout").lower()
        logger.info("[clipai] Output apply start: mode=%s chars=%s", normalized_mode, len(content or ""))
        if normalized_mode == "paste":
            self._paste_without_mutating_clipboard(content)
            return
        if normalized_mode == "clipboard":
            self._copy_without_mutating_clipboard(content)
            return
        if normalized_mode == "popup":
            print(content)
            return
        print(content)

    @staticmethod
    def _paste_without_mutating_clipboard(content: str) -> None:
        session = ClipboardSession()
        session.__enter__()
        try:
            logger.info("[clipai] Output paste: writing clipboard chars=%s", len(content or ""))
            write_clipboard_text(content)
            try:
                maybe_auto_paste()
                logger.info("[clipai] Output paste: auto paste invoked successfully at=%s", time.monotonic())
                session.restore_later(PASTE_RESTORE_DELAY_SEC)
                logger.info(
                    "[clipai] Output paste: deferred clipboard restore scheduled delay_sec=%s",
                    PASTE_RESTORE_DELAY_SEC,
                )
            except RuntimeError as exc:
                session.restore()
                raise OutputModeError(
                    "paste output mode requires 'pynput'. Install it in the active environment "
                    "or run without --apply-output."
                ) from exc
        except Exception:
            session.restore()
            raise

    @staticmethod
    def _copy_without_mutating_clipboard(content: str) -> None:
        with ClipboardSession():
            write_clipboard_text(content)
