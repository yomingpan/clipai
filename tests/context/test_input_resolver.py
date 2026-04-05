from __future__ import annotations

import sys
from types import SimpleNamespace

from clipai.context import input_resolver as input_resolver_module
from clipai.context.input_resolver import InputResolver


class _DummyClipboardSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return None


class _DummyController:
    def press(self, key):
        del key

    def release(self, key):
        del key


def test_read_selected_text_uses_sentinel_not_previous_clipboard(monkeypatch) -> None:
    resolver = InputResolver(copy_delay_sec=0, poll_count=3, poll_delay_sec=0)
    writes: list[str] = []
    clipboard_reads = iter(
        [
            "__CLIPAI_SELECTION_SENTINEL__:token__",
            "same as original clipboard",
        ]
    )

    monkeypatch.setattr(input_resolver_module, "ClipboardSession", _DummyClipboardSession)
    monkeypatch.setattr(input_resolver_module, "write_clipboard_text", lambda text, retries=1, delay=0: writes.append(text))
    monkeypatch.setattr(input_resolver_module, "read_clipboard_text", lambda retries=1, delay=0: next(clipboard_reads, ""))
    monkeypatch.setattr(input_resolver_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(InputResolver, "_selection_sentinel", staticmethod(lambda: "__CLIPAI_SELECTION_SENTINEL__:token__"))
    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(Controller=_DummyController, Key=SimpleNamespace(ctrl="ctrl"))),
    )

    selected = resolver._read_selected_text()

    assert writes == ["__CLIPAI_SELECTION_SENTINEL__:token__"]
    assert selected == "same as original clipboard"


def test_read_selected_text_returns_empty_when_clipboard_never_changes(monkeypatch) -> None:
    resolver = InputResolver(copy_delay_sec=0, poll_count=2, poll_delay_sec=0)
    sentinel = "__CLIPAI_SELECTION_SENTINEL__:token__"

    monkeypatch.setattr(input_resolver_module, "ClipboardSession", _DummyClipboardSession)
    monkeypatch.setattr(input_resolver_module, "write_clipboard_text", lambda text, retries=1, delay=0: None)
    monkeypatch.setattr(input_resolver_module, "read_clipboard_text", lambda retries=1, delay=0: sentinel)
    monkeypatch.setattr(input_resolver_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(InputResolver, "_selection_sentinel", staticmethod(lambda: sentinel))
    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(Controller=_DummyController, Key=SimpleNamespace(ctrl="ctrl"))),
    )

    selected = resolver._read_selected_text()

    assert selected == ""
