from __future__ import annotations

from clipai.platform.clipboard import write_clipboard_text
from clipai.output import maybe_auto_paste
from clipai.capabilities.context.clipboard_session import ClipboardSession


class OutputModeError(RuntimeError):
    pass


class OutputApplier:
    def apply(self, content: str, output_mode: str) -> None:
        normalized_mode = (output_mode or "stdout").lower()
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
        with ClipboardSession():
            write_clipboard_text(content)
            try:
                maybe_auto_paste()
            except RuntimeError as exc:
                raise OutputModeError(
                    "paste output mode requires 'pynput'. Install it in the active environment "
                    "or run without --apply-output."
                ) from exc

    @staticmethod
    def _copy_without_mutating_clipboard(content: str) -> None:
        with ClipboardSession():
            write_clipboard_text(content)
