from __future__ import annotations

import io
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ClipAI.core.models import ExternalWindowRef, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.platform.selection_uia import WindowsSelectionProbe
from ClipAI.platform import selection_uia_worker as worker


SOURCE = SelectionSource(ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")


class Process:
    def __init__(self, payload=None, *, blocked=False, token=None):
        self.payload = payload or {"status": "none"}
        self.blocked = blocked
        self.token = token
        self.returncode = None
        self.killed = False
        self.stdin, self.stdout, self.stderr = io.StringIO(), io.StringIO(), io.StringIO()

    def communicate(self, request=None, timeout=None):
        if not self.killed and self.token is not None:
            self.token.cancel()
        if not self.killed and self.blocked:
            raise subprocess.TimeoutExpired("worker", timeout)
        self.returncode = 0
        return json.dumps(self.payload), ""

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -1


@pytest.mark.parametrize("cancel", [False, True])
def test_hung_provider_is_terminated_and_reaped(cancel):
    token = CancellationToken()
    process = Process(blocked=True, token=token if cancel else None)
    probe = WindowsSelectionProbe(timeout_sec=0.001, process_factory=lambda *a, **kw: process)
    result = probe.probe(SOURCE, token)
    assert result.status == ("cancelled" if cancel else "unknown")
    if not cancel:
        assert result.reason == "uia_timeout"
    assert process.killed
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


def test_worker_receives_identity_only_and_uses_real_interpreter():
    calls = []
    def start(args, **kwargs):
        calls.append((args, kwargs))
        return Process({"status": "selected", "text": "sample", "selection_detected": True})
    result = WindowsSelectionProbe(process_factory=start).probe(SOURCE, None)
    assert result.text == "sample"
    assert calls[0][0][0] == getattr(sys, "_base_executable", sys.executable)
    assert calls[0][1]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


@pytest.mark.parametrize("capability", [True, False, "true"])
def test_worker_copy_capability_is_typed_and_preserved(capability):
    process = Process({"status": "unknown", "copy_selection_only": capability})
    result = WindowsSelectionProbe(process_factory=lambda *a, **kw: process).probe(SOURCE, None)
    assert result.copy_selection_only is (capability is True)


class Range:
    def __init__(self, text="text", *, empty=False, fails=False):
        self.text, self.empty, self.fails = text, empty, fails
    def CompareEndpoints(self, *args):
        return 0 if self.empty else -1
    def Clone(self):
        return Range(self.text, empty=self.empty, fails=self.fails)
    def Compare(self, other):
        return self.text == other.text and self.empty == other.empty
    def GetText(self, limit):
        assert limit == -1
        if self.fails:
            raise RuntimeError("provider failed")
        return self.text


def install_provider(monkeypatch, *, ranges=None, supported=True, password=False, focus_changed=False, root_handle=1):
    pattern = SimpleNamespace(SupportedTextSelection="Single", GetSelection=lambda: ranges)
    root = SimpleNamespace(Current=SimpleNamespace(NativeWindowHandle=root_handle, IsPassword=False, ClassName="Window", FrameworkId="Test"))
    focused = SimpleNamespace(
        Current=SimpleNamespace(NativeWindowHandle=2, IsPassword=password, ClassName="Control", FrameworkId="Test"),
        GetRuntimeId=lambda: (42, 2),
        GetCurrentPropertyValue=lambda _: supported,
        GetCurrentPattern=lambda _: pattern,
    )
    root.GetCurrentPropertyValue = lambda _: False
    class API:
        IsTextPatternAvailableProperty = "TextPattern"
        reads = 0
        @property
        def FocusedElement(self):
            self.reads += 1
            if focus_changed and self.reads > 1:
                return SimpleNamespace(GetRuntimeId=lambda: (42, 3))
            return focused
    api = API()
    automation = SimpleNamespace(
        AutomationElement=api,
        TextPattern=SimpleNamespace(Pattern="TextPattern"),
        TreeWalker=SimpleNamespace(RawViewWalker=SimpleNamespace(GetParent=lambda node: root if node is focused else None)),
    )
    monkeypatch.setitem(sys.modules, "clr", SimpleNamespace(AddReference=lambda _: None))
    monkeypatch.setitem(sys.modules, "System.Windows.Automation", automation)
    monkeypatch.setitem(sys.modules, "System.Windows.Automation.Text", SimpleNamespace(TextPatternRangeEndpoint=SimpleNamespace(Start=0, End=1)))
    monkeypatch.setattr(worker, "capture_windows_source", lambda _: SOURCE)
    return pattern


@pytest.mark.parametrize("ranges,supported,status,reason", [
    ([Range(" \r\ntext\t ")], True, "selected", ""),
    ([Range(empty=True)], True, "none", "uia_caret_only"),
    ([], True, "unknown", "uia_no_ranges"),
    (None, True, "unknown", "uia_no_ranges"),
    ([], False, "unknown", "uia_unsupported"),
    ([Range(fails=True)], True, "unknown", "uia_text_failed"),
])
def test_provider_evidence_distinguishes_none_from_unavailable(monkeypatch, ranges, supported, status, reason):
    install_provider(monkeypatch, ranges=ranges, supported=supported)
    result = worker.read_selection(SOURCE)
    assert (result.status, result.reason) == (status, reason)
    if status == "selected":
        assert result.text == " \ntext\t "
    assert result.selection_detected == (status == "selected" or reason == "uia_text_failed")


@pytest.mark.parametrize("kwargs,reason", [
    ({"password": True}, "uia_protected_or_unavailable"),
    ({"focus_changed": True}, "uia_focus_changed"),
    ({"root_handle": 999}, "uia_source_mismatch"),
])
def test_provider_rejects_wrong_or_changed_source(monkeypatch, kwargs, reason):
    install_provider(monkeypatch, ranges=[Range()], **kwargs)
    result = worker.read_selection(SOURCE)
    assert result.status == "unknown"
    assert result.reason == reason
    assert not result.text


def test_selection_changed_in_same_control_does_not_return_old_text(monkeypatch):
    pattern = install_provider(monkeypatch)
    values = iter([[Range("first")], [Range("second")]])
    pattern.GetSelection = lambda: next(values)
    result = worker.read_selection(SOURCE)
    assert result.status == "unknown"
    assert result.reason == "uia_selection_changed"


@pytest.mark.parametrize("process_name,view_name,focus_changed,expected", [
    ("anki", "MainWebView", False, True),
    ("other", "MainWebView", False, False),
    ("anki", "TopWebView", False, False),
    ("anki", "EditorWebView", False, False),
    ("anki", "MainWebView", True, False),
])
def test_anki_card_without_textpattern_offers_selection_only_copy(monkeypatch, process_name, view_name, focus_changed, expected):
    install_provider(monkeypatch, supported=False)
    api = sys.modules["System.Windows.Automation"]
    focused = api.AutomationElement.FocusedElement
    root = api.TreeWalker.RawViewWalker.GetParent(focused)
    focused.Current.ClassName = "QObject"
    focused.Current.FrameworkId = "Qt"
    root.Current.ClassName = "AnkiQt"
    root.Current.FrameworkId = "Qt"
    webview = SimpleNamespace(Current=SimpleNamespace(
        NativeWindowHandle=0, ClassName=view_name, FrameworkId="Qt", IsPassword=False
    ), GetCurrentPropertyValue=lambda _: False)
    api.TreeWalker.RawViewWalker.GetParent = lambda node: webview if node is focused else root
    monkeypatch.setitem(sys.modules, "System.Diagnostics", SimpleNamespace(
        Process=SimpleNamespace(GetProcessById=lambda _: SimpleNamespace(ProcessName=process_name, Dispose=lambda: None))
    ))
    if focus_changed:
        ids = iter([(42, 2), (42, 3)])
        focused.GetRuntimeId = lambda: next(ids)

    result = worker.read_selection(SOURCE)

    assert result.status == "unknown"  # capability does not prove a selection exists
    assert result.copy_selection_only is expected
    assert result.selection_detected is False
