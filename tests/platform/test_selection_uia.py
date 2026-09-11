from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ClipAI.core.models import ExternalWindowRef, SelectionSource
from ClipAI.core.state import CancellationToken
from ClipAI.platform.selection_uia import WindowsSelectionProbe
from ClipAI.platform import selection_uia_worker as worker


SOURCE = SelectionSource(ExternalWindowRef("hwnd:1", 42, 0), "hwnd:2")


class Process:
    def __init__(self, payload=None, *, blocked=False, token=None):
        self.payload = {"worker_reusable": True, **(payload or {"status": "none"})}
        self.blocked = blocked
        self.token = token
        self.returncode = None
        self.killed = False
        self.requests: list[dict[str, object]] = []
        process = self

        class Input(io.StringIO):
            def flush(self):
                value = self.getvalue()
                if value.endswith("\n"):
                    process.requests.append(json.loads(value.splitlines()[-1]))

        class Output(io.StringIO):
            def readline(self, *args, **kwargs):
                if process.token is not None:
                    process.token.cancel()
                    process.token = None
                while process.blocked and not process.killed:
                    time.sleep(0.001)
                if process.killed:
                    return ""
                return json.dumps(process.payload) + "\n"

        self.stdin, self.stdout, self.stderr = Input(), Output(), io.StringIO()

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -1

    def wait(self, timeout=None):
        return self.returncode


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
    probe = WindowsSelectionProbe(process_factory=start)
    result = probe.probe(SOURCE, None)
    assert result.text == "sample"
    assert calls[0][0][0] == getattr(sys, "_base_executable", sys.executable)
    assert calls[0][1]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    probe.stop()


def test_same_window_reuses_one_owned_worker_in_request_order():
    processes = []

    def start(*args, **kwargs):
        process = Process({"status": "none"})
        processes.append(process)
        return process

    probe = WindowsSelectionProbe(process_factory=start)

    assert probe.probe(SOURCE, None).status == "none"
    assert probe.probe(
        SelectionSource(SOURCE.window, "hwnd:3"), None,
    ).status == "none"

    assert len(processes) == 1
    assert [request["focus_token"] for request in processes[0].requests] == ["hwnd:2", "hwnd:3"]
    assert not processes[0].killed
    probe.stop()
    assert processes[0].killed


def test_owned_worker_retires_after_64_requests():
    processes = []

    def start(*args, **kwargs):
        process = Process({"status": "none"})
        processes.append(process)
        return process

    probe = WindowsSelectionProbe(process_factory=start, max_requests_per_worker=64)

    for _ in range(65):
        assert probe.probe(SOURCE, None).status == "none"

    assert len(processes) == 2
    assert processes[0].killed
    assert len(processes[0].requests) == 64
    assert len(processes[1].requests) == 1
    probe.stop()


def test_switching_top_level_source_retires_previous_worker_before_starting_next():
    lifecycle = []

    class TrackedProcess(Process):
        def kill(self):
            lifecycle.append("retire")
            super().kill()

    def start(*args, **kwargs):
        lifecycle.append("start")
        return TrackedProcess({"status": "none"})

    probe = WindowsSelectionProbe(process_factory=start)
    other = SelectionSource(ExternalWindowRef("hwnd:9", 99, 0), "hwnd:a")

    probe.probe(SOURCE, None)
    probe.probe(other, None)

    assert lifecycle[:3] == ["start", "retire", "start"]
    probe.stop()


@pytest.mark.parametrize("payload", [
    {"status": "broken"},
    {"status": "selected", "text": ""},
    {"status": "none", "text": "unexpected"},
    {"status": "unknown", "copy_selection_only": "true"},
    {"status": "unknown", "reason": "uia_provider_failed", "worker_reusable": False},
    {"status": "unknown", "reason": "uia_text_failed", "selection_detected": True, "worker_reusable": False},
])
def test_invalid_or_failed_owned_worker_is_retired_before_next_request(payload):
    processes = []

    def start(*args, **kwargs):
        process = Process(payload if not processes else {"status": "none"})
        processes.append(process)
        return process

    probe = WindowsSelectionProbe(process_factory=start)

    probe.probe(SOURCE, None)
    assert probe.probe(SOURCE, None).status == "none"

    assert len(processes) == 2
    assert processes[0].killed
    probe.stop()


def test_concurrent_probe_uses_isolated_overflow_worker():
    first_entered = threading.Event()
    release_first = threading.Event()
    processes = []

    class BlockingOutput(io.StringIO):
        def readline(self, *args, **kwargs):
            first_entered.set()
            release_first.wait(1)
            return json.dumps({"status": "none", "worker_reusable": True}) + "\n"

    def start(*args, **kwargs):
        process = Process({"status": "none"})
        if not processes:
            process.stdout = BlockingOutput()
        processes.append(process)
        return process

    probe = WindowsSelectionProbe(process_factory=start)
    thread = threading.Thread(target=lambda: probe.probe(SOURCE, None))
    thread.start()
    assert first_entered.wait(1)

    assert probe.probe(SOURCE, None).status == "none"
    release_first.set()
    thread.join(1)

    assert len(processes) == 2
    assert not processes[0].killed
    assert processes[1].killed
    probe.stop()


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
    native = worker.read_selection(SOURCE)
    result = native.outcome
    assert native.worker_reusable is (reason != "uia_text_failed")
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
    result = worker.read_selection(SOURCE).outcome
    assert result.status == "unknown"
    assert result.reason == reason
    assert not result.text


def test_selection_changed_in_same_control_does_not_return_old_text(monkeypatch):
    pattern = install_provider(monkeypatch)
    values = iter([[Range("first")], [Range("second")]])
    pattern.GetSelection = lambda: next(values)
    result = worker.read_selection(SOURCE).outcome
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
        Process=SimpleNamespace(GetProcessById=lambda _: SimpleNamespace(
            ProcessName=process_name,
            MainModule=SimpleNamespace(FileName=(
                r"C:\Program Files\Anki\anki.exe"
                if process_name == "anki"
                else rf"C:\Program Files\{process_name}\{process_name}.exe"
            )),
            Dispose=lambda: None,
        ))
    ))
    if focus_changed:
        ids = iter([(42, 2), (42, 3)])
        focused.GetRuntimeId = lambda: next(ids)

    result = worker.read_selection(SOURCE).outcome

    assert result.status == "unknown"  # capability does not prove a selection exists
    assert result.copy_selection_only is expected
    assert result.selection_detected is False


@pytest.mark.parametrize("process_name,executable,restored", [
    ("anki", r"C:\Program Files\Anki\anki.exe", True),
    ("pythonw", r"C:\Python313\pythonw.exe", False),
])
def test_gray_anki_card_restores_only_inner_card_focus(
    monkeypatch, process_name, executable, restored,
):
    state = {"focused": None, "set_focus_calls": 0}

    def element(name, handle=0):
        return SimpleNamespace(
            Current=SimpleNamespace(
                NativeWindowHandle=handle,
                IsPassword=False,
                ClassName=name,
                FrameworkId="Qt",
            ),
            GetRuntimeId=lambda: (42, hash(name)),
            GetCurrentPropertyValue=lambda _: False,
        )

    root = element("AnkiQt", 1)
    shell_content = element("QWidget")
    webview = element("MainWebView")
    inner = element("QObject")

    def set_focus():
        state["set_focus_calls"] += 1
        state["focused"] = inner

    inner.SetFocus = set_focus
    state["focused"] = shell_content
    parent = {id(shell_content): root, id(inner): webview, id(webview): root}
    child = {id(root): webview, id(webview): inner}

    class API:
        IsTextPatternAvailableProperty = "TextPattern"

        @property
        def FocusedElement(self):
            return state["focused"]

    walker = SimpleNamespace(
        GetParent=lambda node: parent.get(id(node)),
        GetFirstChild=lambda node: child.get(id(node)),
        GetNextSibling=lambda node: None,
    )
    monkeypatch.setitem(sys.modules, "clr", SimpleNamespace(AddReference=lambda _: None))
    monkeypatch.setitem(sys.modules, "System.Windows.Automation", SimpleNamespace(
        AutomationElement=API(),
        TextPattern=SimpleNamespace(Pattern="TextPattern"),
        TreeWalker=SimpleNamespace(RawViewWalker=walker),
    ))
    monkeypatch.setitem(sys.modules, "System.Windows.Automation.Text", SimpleNamespace(
        TextPatternRangeEndpoint=SimpleNamespace(Start=0, End=1),
    ))
    monkeypatch.setitem(sys.modules, "System.Diagnostics", SimpleNamespace(
        Process=SimpleNamespace(GetProcessById=lambda _: SimpleNamespace(
            ProcessName=process_name,
            MainModule=SimpleNamespace(FileName=executable),
            Dispose=lambda: None,
        )),
    ))
    monkeypatch.setattr(worker, "capture_windows_source", lambda _: SOURCE)

    result = worker.read_selection(SOURCE).outcome

    assert result.focus_restored is restored
    assert result.copy_selection_only is restored
    assert state["set_focus_calls"] == int(restored)


def test_anki_menu_focus_is_rejected_without_repair(monkeypatch):
    state = {"set_focus_calls": 0}

    def element(name, handle=0):
        return SimpleNamespace(
            Current=SimpleNamespace(
                NativeWindowHandle=handle,
                IsPassword=False,
                ClassName=name,
                FrameworkId="Qt",
            ),
            GetRuntimeId=lambda: (42, hash(name)),
            GetCurrentPropertyValue=lambda _: False,
        )

    root = element("AnkiQt", 1)
    menu = element("QMenuBar")
    webview = element("MainWebView")
    inner = element("QObject")
    inner.SetFocus = lambda: state.__setitem__("set_focus_calls", state["set_focus_calls"] + 1)
    parent = {id(menu): root, id(inner): webview, id(webview): root}
    child = {id(root): webview, id(webview): inner}

    class API:
        IsTextPatternAvailableProperty = "TextPattern"
        FocusedElement = menu

    walker = SimpleNamespace(
        GetParent=lambda node: parent.get(id(node)),
        GetFirstChild=lambda node: child.get(id(node)),
        GetNextSibling=lambda node: None,
    )
    monkeypatch.setitem(sys.modules, "clr", SimpleNamespace(AddReference=lambda _: None))
    monkeypatch.setitem(sys.modules, "System.Windows.Automation", SimpleNamespace(
        AutomationElement=API,
        TextPattern=SimpleNamespace(Pattern="TextPattern"),
        TreeWalker=SimpleNamespace(RawViewWalker=walker),
    ))
    monkeypatch.setitem(sys.modules, "System.Windows.Automation.Text", SimpleNamespace(
        TextPatternRangeEndpoint=SimpleNamespace(Start=0, End=1),
    ))
    monkeypatch.setitem(sys.modules, "System.Diagnostics", SimpleNamespace(
        Process=SimpleNamespace(GetProcessById=lambda _: SimpleNamespace(
            ProcessName="anki",
            MainModule=SimpleNamespace(FileName=r"C:\Program Files\Anki\anki.exe"),
            Dispose=lambda: None,
        )),
    ))
    monkeypatch.setattr(worker, "capture_windows_source", lambda _: SOURCE)

    result = worker.read_selection(SOURCE).outcome

    assert result.reason == "uia_unsupported"
    assert not result.focus_restored
    assert not result.copy_selection_only
    assert state["set_focus_calls"] == 0
