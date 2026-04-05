from __future__ import annotations

from clipai.services import output_applier as output_applier_module
from clipai.services.output_applier import OutputApplier


class _DummyClipboardSession:
    def __init__(self) -> None:
        self.events: list[tuple[str, float | None]] = []

    def __enter__(self):
        self.events.append(("enter", None))
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        self.events.append(("exit", None))
        return None

    def restore(self) -> None:
        self.events.append(("restore", None))

    def restore_later(self, delay_sec: float):
        self.events.append(("restore_later", delay_sec))
        return None


def test_paste_output_defers_restore_until_after_auto_paste(monkeypatch) -> None:
    session = _DummyClipboardSession()
    seen: list[tuple[str, str | None]] = []

    monkeypatch.setattr(output_applier_module, "ClipboardSession", lambda: session)
    monkeypatch.setattr(output_applier_module, "write_clipboard_text", lambda text: seen.append(("write", text)))
    monkeypatch.setattr(output_applier_module, "maybe_auto_paste", lambda: seen.append(("paste", None)))

    OutputApplier._paste_without_mutating_clipboard("translated")

    assert session.events[0] == ("enter", None)
    assert seen == [("write", "translated"), ("paste", None)]
    assert ("restore_later", output_applier_module.PASTE_RESTORE_DELAY_SEC) in session.events
    assert ("restore", None) not in session.events
