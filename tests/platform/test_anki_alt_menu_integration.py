"""Opt-in against a user-prepared Anki card; no clipboard or card mutation.

Set CLIPAI_TEST_ANKI_TARGET to ``hwnd:HEX,PID`` and explicitly select integration.
The only injected keys are Alt and the production unassigned menu-mask pair.
"""
from __future__ import annotations

import os
import time

import pytest

from ClipAI.core.commands import OpenUnifiedEntryPanel
from ClipAI.core.models import ExternalWindowRef
from ClipAI.platform.external_window import SystemExternalWindowActivator
from ClipAI.platform import hotkey
from ClipAI.platform.selection_uia import capture_windows_source


@pytest.mark.integration
@pytest.mark.skipif(os.name != "nt" or not os.getenv("CLIPAI_TEST_ANKI_TARGET"), reason="requires explicitly prepared Anki card")
def test_real_anki_alt_hold_preserves_card_focus_and_short_alt_still_opens_menu(monkeypatch):
    import clr
    from pynput.keyboard import Controller, Key

    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        clr.AddReference(f"{assembly}, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35")
    from System.Diagnostics import Process
    from System.Windows.Automation import AutomationElement, TreeWalker

    window, pid = os.environ["CLIPAI_TEST_ANKI_TARGET"].split(",")
    target = ExternalWindowRef(window, int(pid), 0)
    process = Process.GetProcessById(target.process_id)
    try:
        assert str(process.ProcessName).casefold() == "anki"
    finally:
        process.Dispose()
    assert SystemExternalWindowActivator().activate(target, None).activated
    keyboard = Controller()

    def path():
        assert capture_windows_source(target) is not None, "prepared source lost foreground"
        node = AutomationElement.FocusedElement
        classes = []
        for _ in range(32):
            if node is None:
                break
            classes.append(str(node.Current.ClassName))
            if int(node.Current.NativeWindowHandle) == int(window.removeprefix("hwnd:"), 16):
                break
            node = TreeWalker.RawViewWalker.GetParent(node)
        return classes

    def tap():
        assert capture_windows_source(target) is not None
        try:
            keyboard.press(Key.alt_l)
            time.sleep(.05)
        finally:
            keyboard.release(Key.alt_l)
        time.sleep(.15)

    if "QMenuBar" in path():
        tap()
    assert "MainWebView" in path(), "prepare a card before running this test"

    # Only this test process admits synthetic Alt to simulate physical input.
    # Production and any already-running ClipAI still reject injected intents.
    original_gate = hotkey._allow_physical_windows_key
    monkeypatch.setattr(hotkey, "_allow_physical_windows_key", lambda msg, data:
        int(data.vkCode) in (0x12, 0xA4, 0xA5) or original_gate(msg, data))
    events = []
    listener = hotkey.register_hotkeys_with_long_press({}, events.append, entry_panel_enabled=True)
    try:
        listener._listener.wait()
        # Baseline: short Alt is delivered normally and takes menu focus.
        tap()
        assert "QMenuBar" in path()
        tap()
        assert "MainWebView" in path()
        for attempt in range(5):
            assert capture_windows_source(target) is not None
            try:
                keyboard.press(Key.alt_l)
                deadline = time.monotonic() + 2
                while len([e for e in events if isinstance(e, OpenUnifiedEntryPanel)]) <= attempt:
                    assert time.monotonic() < deadline, "hold was not admitted"
                    time.sleep(.01)
                assert "MainWebView" in path(), "focus changed before release"
            finally:
                keyboard.release(Key.alt_l)
            time.sleep(.2)
            assert "MainWebView" in path(), "claimed Alt release moved focus to menu"
        tap()
        assert "QMenuBar" in path(), "short Alt stopped activating menus"
        tap()
        assert "MainWebView" in path()
    finally:
        listener.stop()
        # Restore only this exact prepared window's menu toggle after a failure.
        if capture_windows_source(target) is not None and "QMenuBar" in path():
            tap()
